"""Line-delimited JSON RPC host used by the Tauri desktop shell."""

from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO

from .application import ChatWechatService
from .desktop.bridge import Bridge


def _write(stream: BinaryIO, value: dict[str, Any]) -> None:
    stream.write(
        (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
    )
    stream.flush()


def serve(
    input_stream: BinaryIO | None = None,
    output_stream: BinaryIO | None = None,
) -> int:
    """Serve one stateful application service over stdin/stdout."""
    source = input_stream or sys.stdin.buffer
    sink = output_stream or sys.stdout.buffer
    service = ChatWechatService()
    bridge = Bridge(service)
    try:
        for raw in source:
            request_id: Any = None
            try:
                request = json.loads(raw.decode("utf-8"))
                request_id = request.get("id")
                method = str(request.get("method") or "")
                args = request.get("args") or []
                if method == "shutdown":
                    _write(sink, {"id": request_id, "result": {"ok": True, "data": {}}})
                    break
                if method.startswith("_") or not isinstance(args, list):
                    raise ValueError("invalid RPC request")
                function = getattr(bridge, method, None)
                if function is None or not callable(function):
                    result = {
                        "ok": False,
                        "error": f"桌面接口不可用：{method}",
                        "code": "UnknownMethod",
                    }
                else:
                    result = function(*args)
                _write(sink, {"id": request_id, "result": result})
            except Exception as error:
                _write(
                    sink,
                    {
                        "id": request_id,
                        "result": {
                            "ok": False,
                            "error": "桌面服务请求格式无效",
                            "code": type(error).__name__,
                        },
                    },
                )
    finally:
        service.close()
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
