use super::*;
use std::{
    os::windows::io::{AsHandle, AsRawHandle, FromRawHandle, OwnedHandle},
    time::Instant,
};
use windows_sys::Win32::{
    Foundation::WAIT_OBJECT_0,
    System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE},
};

fn fixture(script: &str) -> (BackendManager, OwnedHandle) {
    let root = env::temp_dir();
    let manager = BackendManager::new(root.clone(), root).unwrap();
    let powershell = PathBuf::from(env::var_os("SystemRoot").unwrap())
        .join("System32/WindowsPowerShell/v1.0/powershell.exe");
    let mut command = Command::new(powershell);
    command.args([
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]);
    let backend = BackendProcess::spawn(command, &manager.job, &manager.closing).unwrap();
    let handle = backend.child.as_handle().try_clone_to_owned().unwrap();
    *manager.process.lock().unwrap() = Some(backend);
    (manager, handle)
}

fn assert_exited(handle: &OwnedHandle) {
    assert_eq!(
        unsafe { WaitForSingleObject(handle.as_raw_handle(), 2000) },
        WAIT_OBJECT_0
    );
}

#[test]
fn shutdown_preserves_the_json_lines_protocol_and_exits_gracefully() {
    let (manager, child) = fixture(
        r#"while ($line = [Console]::ReadLine()) {
            $request = ConvertFrom-Json $line
            $result = @{ id = $request.id; result = @{ ok = $true; data = @{ method = $request.method } } }
            [Console]::WriteLine(($result | ConvertTo-Json -Compress -Depth 5))
            if ($request.method -eq 'shutdown') { break }
        }"#,
    );
    assert_eq!(
        manager.call("ping", vec![]).unwrap()["data"]["method"],
        "ping"
    );
    manager.stop_with_timeout(Duration::from_secs(1));
    assert_exited(&child);
    assert!(
        manager.call("ping", vec![]).is_err(),
        "a stopped manager must never restart its child"
    );
}

#[test]
fn shutdown_is_bounded_when_the_backend_never_answers_shutdown() {
    let (manager, child) = fixture("[Threading.Thread]::Sleep(60000)");
    let started = Instant::now();
    manager.stop_with_timeout(Duration::from_millis(100));
    assert!(started.elapsed() < Duration::from_secs(2));
    assert_exited(&child);
}

#[test]
fn shutdown_interrupts_an_in_flight_rpc_without_waiting_for_its_mutex() {
    let (manager, child) = fixture("[Threading.Thread]::Sleep(60000)");
    let caller = manager.clone();
    let (completed, response) = mpsc::channel();
    thread::spawn(move || {
        let _ = completed.send(caller.call("blocked", vec![]));
    });
    let deadline = Instant::now() + Duration::from_secs(2);
    while manager.process.try_lock().is_ok() {
        assert!(
            Instant::now() < deadline,
            "RPC did not acquire the connection"
        );
        thread::sleep(Duration::from_millis(5));
    }
    let started = Instant::now();
    manager.stop_with_timeout(Duration::from_millis(100));
    assert!(started.elapsed() < Duration::from_secs(2));
    assert_exited(&child);
    assert!(response
        .recv_timeout(Duration::from_secs(2))
        .unwrap()
        .is_err());
}

#[test]
fn shutdown_terminates_backend_descendants() {
    let (manager, parent) = fixture(
        r#"$helper = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
        $child = Start-Process -FilePath $helper -ArgumentList '-NoLogo -NoProfile -NonInteractive -Command [Threading.Thread]::Sleep(60000)' -WindowStyle Hidden -PassThru
        [Console]::WriteLine($child.Id)
        [Threading.Thread]::Sleep(60000)"#,
    );
    let mut line = String::new();
    manager
        .process
        .lock()
        .unwrap()
        .as_mut()
        .unwrap()
        .output
        .read_line(&mut line)
        .unwrap();
    let pid: u32 = line
        .trim()
        .parse()
        .expect("fixture did not start its descendant");
    let raw = unsafe { OpenProcess(PROCESS_SYNCHRONIZE, 0, pid) };
    assert!(!raw.is_null(), "cannot inspect the fixture descendant");
    let descendant = unsafe { OwnedHandle::from_raw_handle(raw) };
    manager.stop_with_timeout(Duration::from_millis(100));
    assert_exited(&parent);
    assert_exited(&descendant);
}
