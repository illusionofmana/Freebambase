# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# Adapted from Blender Cloud Addon (Sybren A. Stüvel, Francesco Siddi, Inês Almeida,
# Antony Riakiotakis) - http://github.com/dfelinto/blender-cloud-addon

"""Manages the asyncio loop"""

import asyncio
import traceback
import concurrent.futures
import logging
import gc

import bpy
from bpy.app.handlers import persistent

log = logging.getLogger(__name__)

# Keeps track of whether a loop-kicking operator is already running.
_stop_after_this_kick = False


def setup_asyncio_executor():
    """Sets up AsyncIO to run properly on each platform"""

    import sys

    if sys.platform == 'win32':
        asyncio.get_event_loop().close()
        # On Windows, the default event loop is SelectorEventLoop, which does
        # not support subprocesses. ProactorEventLoop should be used instead.
        # Source: https://docs.python.org/3/library/asyncio-subprocess.html
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
    else:
        loop = asyncio.get_event_loop()

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    loop.set_default_executor(executor)
    # loop.set_debug(True)


@persistent
def kick_async_loop() -> bool:
    """Performs a single iteration of the asyncio event loop.

    :return: whether the asyncio loop should stop after this kick.
    """

    global _stop_after_this_kick
    loop = asyncio.get_event_loop()

    # Even when we want to stop, we always need to do one more
    # 'kick' to handle task-done callbacks.
    _stop_after_this_kick = False

    if loop.is_closed():
        log.warning('loop closed, stopping immediately.')
        return True

    all_tasks = None
    if bpy.app.version >= (2, 92):
        all_tasks = asyncio.all_tasks(loop)
    else:
        all_tasks = asyncio.Task.all_tasks()

    if not len(all_tasks):
        log.debug('no more scheduled tasks, stopping after this kick.')
        _stop_after_this_kick = True

    elif all(task.done() for task in all_tasks):
        log.debug('all %i tasks are done, fetching results and stopping after this kick.',
                  len(all_tasks))
        _stop_after_this_kick = True

        # Clean up circular references between tasks.
        gc.collect()

        for task_idx, task in enumerate(all_tasks):
            if not task.done():
                continue

            # noinspection PyBroadException
            try:
                res = task.result()
                log.debug('   task #%i: result=%r', task_idx, res)
            except asyncio.CancelledError:
                # No problem, we want to stop anyway.
                log.debug('   task #%i: cancelled', task_idx)
            except Exception:
                print('{}: resulted in exception'.format(task))
                traceback.print_exc()

            # for ref in gc.get_referrers(task):
            #     log.debug('      - referred by %s', ref)

    loop.stop()
    loop.run_forever()

    return 0.00001


def ensure_async_loop():
    log.debug('Starting asyncio loop')
    bpy.app.timers.register(kick_async_loop, persistent=True)


def erase_async_loop():
    global _loop_kicking_operator_running

    log.debug('Erasing async loop')

    loop = asyncio.get_event_loop()
    loop.stop()

    if bpy.app.timers.is_registered(kick_async_loop):
        bpy.app.timers.unregister(kick_async_loop)

    # loop synchronously for a bit so that the server can fully shut down. normally doesn't take long
    ticks = 0
    while ticks < 9000:
        kick_async_loop()

        if _stop_after_this_kick:
            break

        ticks = ticks + 1
    else:
        bpy.ops.pribambase.report(message_type='ERROR', message="Failed to close the connection. Sometimes that blocks new connections until blender restarts")
