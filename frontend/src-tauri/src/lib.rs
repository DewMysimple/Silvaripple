use serde_json::{json, Value};
use std::{
    env,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, RunEvent, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const CREATE_NO_WINDOW: u32 = 0x0800_0000;

struct BackendProcess {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    request_id: u64,
}

impl BackendProcess {
    fn start(working_directory: &Path, resource_dir: &Path) -> Result<Self, String> {
        let mut command = if let Ok(executable) = env::var("CHATWECHAT_BACKEND") {
            Command::new(executable)
        } else if cfg!(debug_assertions) {
            let mut value =
                Command::new(env::var("CHATWECHAT_PYTHON").unwrap_or_else(|_| "python".to_owned()));
            value.args(["-m", "chatwechat"]);
            value
        } else {
            let current = env::current_exe().map_err(|error| error.to_string())?;
            let directory = current
                .parent()
                .ok_or_else(|| "无法定位 ChatWechat 安装目录".to_owned())?;
            let candidates = [
                directory.join("chatwechat-backend.exe"),
                directory.join("binaries").join("chatwechat-backend.exe"),
                resource_dir.join("chatwechat-backend.exe"),
            ];
            let executable = candidates
                .into_iter()
                .find(|path| path.is_file())
                .ok_or_else(|| "ChatWechat 后端组件缺失，请重新安装。".to_owned())?;
            Command::new(executable)
        };

        command
            .arg("--rpc")
            .current_dir(working_directory)
            .env("CHATWECHAT_RESOURCE_DIR", resource_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(if cfg!(debug_assertions) {
                Stdio::inherit()
            } else {
                Stdio::null()
            });
        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);

        let mut child = command
            .spawn()
            .map_err(|error| format!("无法启动 ChatWechat 后端：{error}"))?;
        let input = child
            .stdin
            .take()
            .ok_or_else(|| "无法连接 ChatWechat 后端输入".to_owned())?;
        let output = child
            .stdout
            .take()
            .ok_or_else(|| "无法连接 ChatWechat 后端输出".to_owned())?;
        Ok(Self {
            child,
            input,
            output: BufReader::new(output),
            request_id: 0,
        })
    }

    fn call(&mut self, method: &str, args: Vec<Value>) -> Result<Value, String> {
        self.request_id += 1;
        let request_id = self.request_id;
        serde_json::to_writer(
            &mut self.input,
            &json!({"id": request_id, "method": method, "args": args}),
        )
        .map_err(|error| error.to_string())?;
        self.input
            .write_all(b"\n")
            .and_then(|_| self.input.flush())
            .map_err(|error| format!("ChatWechat 后端连接已断开：{error}"))?;

        let mut line = String::new();
        self.output
            .read_line(&mut line)
            .map_err(|error| format!("读取 ChatWechat 后端响应失败：{error}"))?;
        if line.is_empty() {
            return Err("ChatWechat 后端意外退出，请重新启动应用。".to_owned());
        }
        let response: Value =
            serde_json::from_str(&line).map_err(|_| "ChatWechat 后端返回了无效响应".to_owned())?;
        if response.get("id").and_then(Value::as_u64) != Some(request_id) {
            return Err("ChatWechat 后端响应顺序异常".to_owned());
        }
        response
            .get("result")
            .cloned()
            .ok_or_else(|| "ChatWechat 后端响应缺少结果".to_owned())
    }

    fn stop(&mut self) {
        let _ = self.call("shutdown", Vec::new());
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            if self.child.try_wait().ok().flatten().is_some() {
                return;
            }
            thread::sleep(Duration::from_millis(25));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

#[derive(Clone)]
struct BackendManager {
    process: Arc<Mutex<Option<BackendProcess>>>,
    working_directory: PathBuf,
    resource_dir: PathBuf,
}

impl BackendManager {
    fn new(working_directory: PathBuf, resource_dir: PathBuf) -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
            working_directory,
            resource_dir,
        }
    }

    fn call(&self, method: &str, args: Vec<Value>) -> Result<Value, String> {
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "ChatWechat 后端状态不可用".to_owned())?;
        if guard.is_none() {
            *guard = Some(BackendProcess::start(
                &self.working_directory,
                &self.resource_dir,
            )?);
        }
        let result = guard
            .as_mut()
            .ok_or_else(|| "ChatWechat 后端尚未启动".to_owned())?
            .call(method, args);
        if result.is_err() {
            if let Some(process) = guard.as_mut() {
                let _ = process.child.kill();
            }
            *guard = None;
        }
        result
    }

    fn stop(&self) {
        if let Ok(mut guard) = self.process.lock() {
            if let Some(process) = guard.as_mut() {
                process.stop();
            }
            *guard = None;
        }
    }
}

#[tauri::command]
async fn bridge_invoke(
    state: State<'_, BackendManager>,
    method: String,
    args: Vec<Value>,
) -> Result<Value, String> {
    let manager = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || manager.call(&method, args))
        .await
        .map_err(|error| format!("ChatWechat 后端任务失败：{error}"))?
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(debug_assertions)]
    let repository_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("frontend/src-tauri must be inside the repository")
        .to_path_buf();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(move |app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .map_err(|error| format!("无法定位 ChatWechat 资源目录：{error}"))?;
            #[cfg(debug_assertions)]
            let working_directory = repository_root.clone();
            #[cfg(not(debug_assertions))]
            let working_directory = resource_dir.clone();
            app.manage(BackendManager::new(working_directory, resource_dir));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![bridge_invoke])
        .build(tauri::generate_context!())
        .expect("error while building ChatWechat");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit) {
            handle.state::<BackendManager>().stop();
        }
    });
}
