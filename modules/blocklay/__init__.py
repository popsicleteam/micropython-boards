import asyncio

__all__ = (
    "call",
    "stop",
    "task",
    "receiver",
    "broadcast",
    "start",
    "shutdown",
)

_task_groups = None
_receiver_groups = None

asyncio.new_event_loop()


def call(task_script, task_group_name=None):
    event_loop = asyncio.get_event_loop()
    global _task_groups
    if _task_groups is None:
        _task_groups = {}

    if task_group_name is None:
        task_group_name = task_script.__globals__["__file__"]
    task_group = _task_groups.setdefault(task_group_name, [])
    task_group.append(event_loop.create_task(task_script()))


def stop(task_group_name):
    if _task_groups is not None:
        task_group = _task_groups.setdefault(task_group_name, [])
        current_task = asyncio.current_task()
        for task in task_group:
            if task is not current_task:
                task.cancel()
        task_group.clear()
        task_group.append(current_task)


def task(condition_flag=None, *args):
    if condition_flag is None:
        return call

    def condition_task(task_script):
        async def condition():
            while True:
                if await condition_flag():
                    call(task_script)
                await asyncio.sleep_ms(5)

        call(condition, "blocklay")

    return condition_task


def receiver(msg):
    global _receiver_groups
    if _receiver_groups is None:
        _receiver_groups = {}

    receiver_scripts = _receiver_groups.setdefault(msg, [])

    def receiver_task(task_script):
        receiver_scripts.append(task_script)

    return receiver_task


def broadcast(msg):
    if _receiver_groups is not None:
        receiver_scripts = _receiver_groups.setdefault(msg, [])
        for task_script in receiver_scripts:
            call(task_script)


def reset():
    event_loop = asyncio.get_event_loop()
    event_loop.stop()
    event_loop.close()

    global _task_groups, _receiver_groups
    if _task_groups is not None:
        _task_groups.clear()
        _task_groups = None

    if _receiver_groups is not None:
        for receiver_scripts in _receiver_groups.values():
            receiver_scripts.clear()
        _receiver_groups.clear()
        _receiver_groups = None


def start():
    event_loop = asyncio.get_event_loop()
    try:
        event_loop.run_forever()
    except KeyboardInterrupt:
        print("Shutdown, Bye!")
    finally:
        reset()


def shutdown():
    raise KeyboardInterrupt
