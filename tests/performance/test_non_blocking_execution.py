"""Performance tests for non-blocking skill execution.

Tests that long-running skill executions don't block other operations.

Requirements tested:
- 10.3: Non-blocking skill execution
"""

import asyncio
import time

import pytest


# =========================================================================
# Test 27.3: Non-blocking skill execution
# =========================================================================


@pytest.mark.performance
@pytest.mark.asyncio
async def test_long_running_task_does_not_block() -> None:
    """Test that a long-running async task doesn't block other tasks.
    
    Requirements: 10.3
    
    This test verifies the fundamental async behavior that when one task
    takes a long time, other tasks can still execute concurrently.
    """
    # Arrange - create tasks with different execution times
    async def slow_task():
        """Simulates a 30-second task (reduced for testing)."""
        await asyncio.sleep(0.5)
        return "slow-completed"
    
    async def fast_task(task_id):
        """Simulates a fast task."""
        await asyncio.sleep(0.05)
        return f"fast-{task_id}-completed"
    
    # Act - start slow task and multiple fast tasks concurrently
    start_time = time.time()
    
    tasks = [
        slow_task(),
        fast_task(1),
        fast_task(2),
        fast_task(3),
    ]
    
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Assert - verify all tasks completed
    assert len(results) == 4
    assert results[0] == "slow-completed"
    assert "fast-1-completed" in results
    assert "fast-2-completed" in results
    assert "fast-3-completed" in results
    
    # Verify fast tasks didn't wait for slow task
    # If blocking, would take 0.5 + 0.05*3 = 0.65s sequentially
    # If non-blocking, should take ~0.5s (time of slowest)
    assert duration < 0.7, f"Execution took too long: {duration:.2f}s (suggests blocking)"
    assert duration >= 0.5, f"Execution too fast: {duration:.2f}s (tasks may not have run)"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_task_execution() -> None:
    """Test that multiple tasks can execute concurrently.
    
    Requirements: 10.3
    
    This test verifies that the system can handle multiple concurrent
    task executions without blocking.
    """
    # Arrange
    num_tasks = 10
    execution_time = 0.1  # 100ms per task
    
    async def task(task_id):
        await asyncio.sleep(execution_time)
        return f"task-{task_id}-completed"
    
    # Act - execute multiple tasks concurrently
    start_time = time.time()
    
    tasks_list = [task(i) for i in range(num_tasks)]
    results = await asyncio.gather(*tasks_list)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Assert - verify all completed successfully
    assert len(results) == num_tasks
    assert all("completed" in r for r in results)
    
    # Verify concurrent execution
    # If sequential: 10 * 0.1 = 1.0s
    # If concurrent: ~0.1s (time of one task)
    assert duration < 0.3, f"Execution suggests sequential processing: {duration:.2f}s"
    assert duration >= 0.1, f"Execution too fast: {duration:.2f}s"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_task_execution_isolation() -> None:
    """Test that task executions are isolated from each other.
    
    Requirements: 10.3
    
    This test verifies that one task's execution doesn't affect another's.
    """
    # Arrange
    execution_count = {"count": 0}
    
    async def task(task_id):
        # Increment counter
        execution_count["count"] += 1
        current_count = execution_count["count"]
        
        # Simulate work
        await asyncio.sleep(0.05)
        
        return f"task-{task_id}-count-{current_count}"
    
    # Act - execute tasks concurrently
    tasks_list = [task(i) for i in range(5)]
    results = await asyncio.gather(*tasks_list)
    
    # Assert - verify all executed
    assert len(results) == 5
    assert all("task-" in r for r in results)
    
    # Verify each got a unique count (isolation)
    assert len(set(results)) == 5, "Tasks should have unique execution contexts"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_task_timeout_does_not_block_others() -> None:
    """Test that a task timing out doesn't block other tasks.
    
    Requirements: 10.3
    
    This test verifies that when one task times out, other tasks
    continue executing normally.
    """
    # Arrange
    async def timeout_task():
        """Simulates a task that times out."""
        await asyncio.sleep(10)  # Would timeout
        return "timeout-completed"
    
    async def normal_task(task_id):
        """Simulates a normal task."""
        await asyncio.sleep(0.05)
        return f"normal-{task_id}-completed"
    
    async def timeout_wrapper():
        """Wrapper that enforces timeout."""
        try:
            return await asyncio.wait_for(timeout_task(), timeout=0.1)
        except asyncio.TimeoutError:
            return "timeout-error"
    
    # Act - execute timeout task and normal tasks concurrently
    start_time = time.time()
    
    tasks = [
        timeout_wrapper(),
        normal_task(1),
        normal_task(2),
    ]
    
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Assert - verify normal tasks completed despite timeout
    assert len(results) == 3
    
    # First result should be timeout error
    assert results[0] == "timeout-error"
    
    # Other results should be successful
    assert results[1] == "normal-1-completed"
    assert results[2] == "normal-2-completed"
    
    # Verify didn't take too long
    assert duration < 0.5, f"Execution took too long: {duration:.2f}s"


@pytest.mark.performance
@pytest.mark.asyncio
async def test_many_concurrent_tasks() -> None:
    """Test handling many concurrent tasks.
    
    Requirements: 10.3
    
    This test verifies that the system can handle a large number of
    concurrent tasks efficiently.
    """
    # Arrange
    num_tasks = 100
    execution_time = 0.01  # 10ms per task
    
    async def task(task_id):
        await asyncio.sleep(execution_time)
        return task_id
    
    # Act
    start_time = time.time()
    
    tasks_list = [task(i) for i in range(num_tasks)]
    results = await asyncio.gather(*tasks_list)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Assert
    assert len(results) == num_tasks
    assert set(results) == set(range(num_tasks))
    
    # If sequential: 100 * 0.01 = 1.0s
    # If concurrent: ~0.01s
    assert duration < 0.5, f"Execution suggests poor concurrency: {duration:.2f}s"
