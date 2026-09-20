use serde_json::{json, Value};
use std::{
    env,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::Duration,
};
use tauri::{Manager, RunEvent, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
mod windows_job;
#[cfg(windows)]
use windows_job::{resume_suspended_child, WindowsJob};
#[cfg(windows)]
use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};

#[cfg(all(test, windows))]
mod lifecycle_tests;

struct BackendProcess {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    request_id: u64,
}

impl BackendProcess {
    fn start(
        working_directory: &Path,
        resource_dir: &Path,
        #[cfg(windows)] job: &WindowsJob,
        closing: &AtomicBool,
    ) -> Result<Self, String> {
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
                .ok_or_else(|| "无法定位 ChatWechat 应用目录".to_owned())?;
            let candidates = [
                directory.join("chatwechat-backend.exe"),
                directory.join("binaries").join("chatwechat-backend.exe"),
                resource_dir.join("chatwechat-backend.exe"),
            ];
            let executable = candidates
                .into_iter()
                .find(|path| path.is_file())
                .ok_or_else(|| "ChatWechat 后端组件缺失，请重新完整解压应用。".to_owned())?;
            Command::new(executable)
        };

        command
            .arg("--rpc")
            .current_dir(working_directory)
            .env("CHATWECHAT_RESOURCE_DIR", resource_dir);
        Self::spawn(
            command,
            #[cfg(windows)]
            job,
            closing,
        )
    }

    fn spawn(
        mut command: Command,
        #[cfg(windows)] job: &WindowsJob,
        closing: &AtomicBool,
    ) -> Result<Self, String> {
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(if cfg!(debug_assertions) {
                Stdio::inherit()
            } else {
                Stdio::null()
            });
        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);

        let mut child = command
            .spawn()
            .map_err(|error| format!("无法启动 ChatWechat 后端：{error}"))?;
        #[cfg(windows)]
        let prepare = job.attach(&child).and_then(|_| {
            if closing.load(Ordering::SeqCst) {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::Interrupted,
                    "Application is closing",
                ));
            }
            resume_suspended_child(&child)
        });
        #[cfg(not(windows))]
        let prepare: std::io::Result<()> = if closing.load(Ordering::SeqCst) {
            Err(std::io::Error::new(
                std::io::ErrorKind::Interrupted,
                "Application is closing",
            ))
        } else {
            Ok(())
        };
        if let Err(error) = prepare {
            let _ = child.kill();
            let _ = child.wait();
            return Err(format!("无法管理 ChatWechat 后端进程：{error}"));
        }
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

    fn stop_gracefully(&mut self) {
        let _ = self.call("shutdown", Vec::new());
        let _ = self.child.wait();
    }
}

#[derive(Clone)]
struct BackendManager {
    process: Arc<Mutex<Option<BackendProcess>>>,
    closing: Arc<AtomicBool>,
    #[cfg(windows)]
    job: Arc<WindowsJob>,
    working_directory: PathBuf,
    resource_dir: PathBuf,
}

impl BackendManager {
    fn new(working_directory: PathBuf, resource_dir: PathBuf) -> Result<Self, String> {
        Ok(Self {
            process: Arc::new(Mutex::new(None)),
            closing: Arc::new(AtomicBool::new(false)),
            #[cfg(windows)]
            job: Arc::new(
                WindowsJob::new().map_err(|error| format!("无法创建后端进程管理器：{error}"))?,
            ),
            working_directory,
            resource_dir,
        })
    }

    fn call(&self, method: &str, args: Vec<Value>) -> Result<Value, String> {
        let mut guard = self
            .process
            .lock()
            .map_err(|_| "ChatWechat 后端状态不可用".to_owned())?;
        if self.closing.load(Ordering::SeqCst) {
            return Err("ChatWechat 正在关闭".to_owned());
        }
        if guard.is_none() {
            *guard = Some(BackendProcess::start(
                &self.working_directory,
                &self.resource_dir,
                #[cfg(windows)]
                &self.job,
                &self.closing,
            )?);
        }
        let result = guard
            .as_mut()
            .ok_or_else(|| "ChatWechat 后端尚未启动".to_owned())?
            .call(method, args);
        if result.is_err() {
            #[cfg(windows)]
            self.job.terminate();
            if let Some(process) = guard.as_mut() {
                let _ = process.child.kill();
                let _ = process.child.wait();
            }
            *guard = None;
        }
        result
    }

    fn stop(&self) {
        self.stop_with_timeout(Duration::from_secs(2));
    }

    fn stop_with_timeout(&self, grace: Duration) {
        if self.closing.swap(true, Ordering::SeqCst) {
            return;
        }
        let process = self.process.clone();
        let (done, receiver) = mpsc::channel();
        // Both the mutex and the shutdown RPC can block. Keep them off the
        // window thread; only this bounded channel wait is on the exit path.
        thread::spawn(move || {
            if let Ok(mut guard) = process.lock() {
                if let Some(process) = guard.as_mut() {
                    process.stop_gracefully();
                }
                *guard = None;
            }
            let _ = done.send(());
        });
        let exited = receiver.recv_timeout(grace).is_ok();
        #[cfg(windows)]
        self.job.terminate();
        #[cfg(not(windows))]
        if let Ok(mut guard) = self.process.try_lock() {
            if let Some(process) = guard.as_mut() {
                let _ = process.child.kill();
            }
        }
        if !exited {
            // Killing the process tree closes inherited stdout handles too,
            // releasing blocked RPC readers and allowing the child to be reaped.
            let _ = receiver.recv_timeout(Duration::from_secs(1));
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
            app.manage(BackendManager::new(working_directory, resource_dir)?);
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
