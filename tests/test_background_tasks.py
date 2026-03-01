"""Background tasks tests — covers request.state.background_tasks scheduling.

Tests cover:
  - Background task scheduling
  - Sync and async background tasks
  - Task execution timing (after response)
  - Callable vs direct task objects
  - Multiple background tasks
"""
# pyright: reportUnusedFunction=false

import asyncio

from starlette.requests import Request
from starlette.testclient import TestClient
from wilrise import Use, Wilrise


class TestBackgroundTasks:
    """Test background task scheduling and execution."""

    def test_sync_background_task_executes(self) -> None:
        """Sync background task executes after response is sent."""
        executed = []

        def background_task():
            executed.append("task1")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_task(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(background_task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post("/", json={"jsonrpc": "2.0", "method": "trigger_task", "id": 1})
        assert r.status_code == 200
        assert r.json()["result"] == "ok"
        assert "task1" in executed

    def test_async_background_task_executes(self) -> None:
        """Async background task executes after response is sent."""
        executed = []

        async def async_task():
            executed.append("async_task")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_async_task(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(async_task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_async_task", "id": 1}
        )
        assert r.status_code == 200
        assert r.json()["result"] == "ok"
        assert "async_task" in executed

    def test_multiple_background_tasks(self) -> None:
        """Multiple background tasks execute in order."""
        executed = []

        def task1():
            executed.append(1)

        def task2():
            executed.append(2)

        def task3():
            executed.append(3)

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_multiple(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.extend([task1, task2, task3])
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_multiple", "id": 1}
        )
        assert r.status_code == 200
        assert executed == [1, 2, 3]

    def test_callable_background_task(self) -> None:
        """Background task as callable (lambda or function reference)."""
        executed = []

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_callable(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(lambda: executed.append("lambda"))
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_callable", "id": 1}
        )
        assert r.status_code == 200
        assert "lambda" in executed

    def test_background_task_with_exception_in_async_task(self) -> None:
        """Async background task exception doesn't affect response (fire-and-forget)."""
        executed = []

        async def failing_async_task():
            executed.append("attempted")
            raise RuntimeError("Task failed")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_failing_task(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(failing_async_task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_failing_task", "id": 1}
        )
        assert r.status_code == 200
        assert r.json()["result"] == "ok"
        assert "attempted" in executed

    def test_background_task_with_args(self) -> None:
        """Background task can capture arguments via closure."""
        results = []

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_with_args(req: Request = Use(get_request)) -> str:
            value1 = 42
            value2 = "hello"

            def task1():
                results.append(value1)

            def task2():
                results.append(value2)

            req.state.background_tasks.extend([task1, task2])
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_with_args", "id": 1}
        )
        assert r.status_code == 200
        assert 42 in results
        assert "hello" in results

    def test_background_task_accesses_request_state(self) -> None:
        """Background task can access request state via closure."""
        results = []

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_with_state(req: Request = Use(get_request)) -> str:
            req.state.custom_data = "test_value"

            def task():
                results.append(req.state.custom_data)

            req.state.background_tasks.append(task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_with_state", "id": 1}
        )
        assert r.status_code == 200
        assert "test_value" in results

    def test_background_task_in_notification(self) -> None:
        """Background tasks execute even for notifications (no response)."""
        executed = []

        def notification_task():
            executed.append("notified")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def notify(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(notification_task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post("/", json={"jsonrpc": "2.0", "method": "notify"})
        assert r.status_code == 204
        assert "notified" in executed

    def test_background_task_with_error_response(self) -> None:
        """Background tasks execute even when method returns error."""
        executed = []

        def error_task():
            executed.append("error_handled")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def failing_method(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(error_task)
            raise ValueError("Method failed")

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "failing_method", "id": 1}
        )
        assert r.status_code == 200
        assert r.json()["error"]["code"] == -32603
        assert "error_handled" in executed

    def test_empty_background_tasks_list(self) -> None:
        """Empty background_tasks list doesn't cause issues."""
        app = Wilrise()

        @app.method
        def no_tasks() -> str:
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post("/", json={"jsonrpc": "2.0", "method": "no_tasks", "id": 1})
        assert r.status_code == 200
        assert r.json()["result"] == "ok"

    def test_background_task_mixed_sync_async(self) -> None:
        """Mix of sync and async background tasks."""
        executed = []

        def sync_task():
            executed.append("sync")

        async def async_task():
            executed.append("async")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_mixed(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.extend([sync_task, async_task])
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_mixed", "id": 1}
        )
        assert r.status_code == 200
        assert "sync" in executed
        assert "async" in executed

    def test_background_task_with_dependency_injection(self) -> None:
        """Background task can use dependency-injected values via closure."""
        results = []

        def get_db(request: Request) -> str:
            return "db_connection"

        def get_request(r: Request) -> Request:
            return r

        app = Wilrise()

        @app.method
        def trigger_with_di(
            db: str = Use(get_db), req: Request = Use(get_request)
        ) -> str:
            def task():
                results.append(db)

            req.state.background_tasks.append(task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_with_di", "id": 1}
        )
        assert r.status_code == 200
        assert "db_connection" in results

    def test_background_task_execution_order(self) -> None:
        """Background tasks execute in the order they were added."""
        order = []

        def task1():
            order.append(1)

        def task2():
            order.append(2)

        def task3():
            order.append(3)

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_ordered(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.extend([task1, task2, task3])
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_ordered", "id": 1}
        )
        assert r.status_code == 200
        assert order == [1, 2, 3]

    def test_background_task_with_batch_request(self) -> None:
        """Background tasks execute for each request in a batch."""
        executed = []

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def method1(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(lambda: executed.append("method1"))
            return "ok1"

        @app.method
        def method2(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(lambda: executed.append("method2"))
            return "ok2"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json=[
                {"jsonrpc": "2.0", "method": "method1", "id": 1},
                {"jsonrpc": "2.0", "method": "method2", "id": 2},
            ],
        )
        assert r.status_code == 200
        assert "method1" in executed
        assert "method2" in executed

    def test_background_task_with_long_running(self) -> None:
        """Long-running background task doesn't block response."""
        results = []

        def long_task():
            import time

            time.sleep(0.05)
            results.append("done")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_long(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(long_task)
            return "immediate"

        client = TestClient(app.as_asgi())
        r = client.post("/", json={"jsonrpc": "2.0", "method": "trigger_long", "id": 1})
        assert r.status_code == 200
        assert r.json()["result"] == "immediate"
        assert "done" in results

    def test_background_task_with_coroutine_function(self) -> None:
        """Async function (not coroutine object) is handled correctly."""
        executed = []

        async def async_func():
            executed.append("async_func")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_coroutine_func(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(async_func)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "trigger_coroutine_func", "id": 1}
        )
        assert r.status_code == 200
        assert "async_func" in executed

    def test_background_task_replaces_list(self) -> None:
        """Background tasks list can be replaced entirely."""
        executed = []

        def task1():
            executed.append(1)

        def task2():
            executed.append(2)

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def replace_tasks(req: Request = Use(get_request)) -> str:
            req.state.background_tasks = [task1, task2]
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/", json={"jsonrpc": "2.0", "method": "replace_tasks", "id": 1}
        )
        assert r.status_code == 200
        assert executed == [1, 2]

    def test_background_task_with_async_method(self) -> None:
        """Background tasks work with async methods."""
        executed = []

        async def bg_task():
            executed.append("async_bg")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        async def async_method(req: Request = Use(get_request)) -> str:
            await asyncio.sleep(0)
            req.state.background_tasks.append(bg_task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post("/", json={"jsonrpc": "2.0", "method": "async_method", "id": 1})
        assert r.status_code == 200
        assert "async_bg" in executed

    def test_background_task_callable_returning_coroutine(self) -> None:
        """Callable returning coroutine is handled correctly."""
        executed = []

        async def make_async_task():
            executed.append("callable_coroutine")

        app = Wilrise()

        def get_request(r: Request) -> Request:
            return r

        @app.method
        def trigger_callable_coroutine(req: Request = Use(get_request)) -> str:
            req.state.background_tasks.append(make_async_task)
            return "ok"

        client = TestClient(app.as_asgi())
        r = client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "trigger_callable_coroutine", "id": 1},
        )
        assert r.status_code == 200
        assert "callable_coroutine" in executed
