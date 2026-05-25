"""Tests for scheduler module."""

from unittest.mock import MagicMock, patch

import pytest

from stonks_trading.shared.scheduler import Scheduler


class TestScheduler:
    """Tests for Scheduler class."""

    def test_initialization(self) -> None:
        """Test scheduler initializes correctly."""
        scheduler = Scheduler()
        assert scheduler._running is False
        assert scheduler._scheduler is not None

    def test_start(self) -> None:
        """Test starting the scheduler."""
        scheduler = Scheduler()

        with patch.object(scheduler._scheduler, 'start') as mock_start:
            scheduler.start()

            assert scheduler._running is True
            mock_start.assert_called_once()

    def test_start_already_running(self) -> None:
        """Test starting when already running."""
        scheduler = Scheduler()
        scheduler._running = True

        with patch.object(scheduler._scheduler, 'start') as mock_start:
            scheduler.start()

            # Should not call start again
            mock_start.assert_not_called()

    def test_stop(self) -> None:
        """Test stopping the scheduler."""
        scheduler = Scheduler()
        scheduler._running = True

        with patch.object(scheduler._scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()

            assert scheduler._running is False
            mock_shutdown.assert_called_once_with(wait=False)

    def test_stop_not_running(self) -> None:
        """Test stopping when not running."""
        scheduler = Scheduler()
        scheduler._running = False

        with patch.object(scheduler._scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()

            # Should not call shutdown
            mock_shutdown.assert_not_called()

    def test_is_running_property(self) -> None:
        """Test is_running property."""
        scheduler = Scheduler()
        assert scheduler.is_running is False

        scheduler._running = True
        assert scheduler.is_running is True

    def test_remove_job(self) -> None:
        """Test removing a job."""
        scheduler = Scheduler()

        with patch.object(scheduler._scheduler, 'remove_job') as mock_remove:
            scheduler.remove_job("test_job")

            mock_remove.assert_called_once_with("test_job")

    def test_list_jobs(self) -> None:
        """Test listing jobs."""
        scheduler = Scheduler()

        # Create mock jobs
        mock_job = MagicMock()
        mock_job.id = "job_1"
        mock_job.name = "Test Job"
        mock_job.next_run_time.isoformat.return_value = "2024-01-15T00:00:00"

        with patch.object(scheduler._scheduler, 'get_jobs', return_value=[mock_job]):
            jobs = scheduler.list_jobs()

            assert len(jobs) == 1
            assert jobs[0]["id"] == "job_1"
            assert jobs[0]["name"] == "Test Job"
