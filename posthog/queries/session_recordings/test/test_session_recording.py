import random
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from django.http import HttpRequest
from django.utils.timezone import now
from freezegun import freeze_time
from rest_framework.request import Request

from posthog.models import Filter
from posthog.models.session_recording.metadata import SessionRecordingEvent
from posthog.models.team import Team
from posthog.queries.session_recordings.session_recording_events import RecordingMetadata, SessionRecordingEvents
from posthog.session_recordings.session_recording_helpers import (
    DecompressedRecordingData,
)
from posthog.session_recordings.test.test_factory import create_snapshots, create_snapshot
from posthog.test.base import APIBaseTest, ClickhouseTestMixin


def create_recording_filter(session_recording_id, limit=None, offset=None) -> Filter:
    params = {}
    if limit:
        params["limit"] = limit
    if offset:
        params["offset"] = offset
    build_req = HttpRequest()
    build_req.META = {"HTTP_HOST": "www.testserver"}

    req = Request(
        build_req, f"/api/event/session_recording?session_recording_id={session_recording_id}{urlencode(params)}"  # type: ignore
    )
    return Filter(request=req, data=params)


class TestClickhouseSessionRecording(ClickhouseTestMixin, APIBaseTest):

    maxDiff = None

    def test_get_snapshots(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            create_snapshot(
                has_full_snapshot=False, distinct_id="user", session_id="1", timestamp=now(), team_id=self.team.id
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now() + relativedelta(seconds=10),
                team_id=self.team.id,
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user2",
                session_id="2",
                timestamp=now() + relativedelta(seconds=20),
                team_id=self.team.id,
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now() + relativedelta(seconds=30),
                team_id=self.team.id,
            )

            filter = create_recording_filter("1")
            recording: DecompressedRecordingData = SessionRecordingEvents(
                team=self.team, session_recording_id="1"
            ).get_snapshots(filter.limit, filter.offset)

            self.assertEqual(
                recording["snapshot_data_by_window_id"],
                {
                    "": [
                        {"timestamp": 1600000000000, "type": 3, "data": {"source": 0}},
                        {"timestamp": 1600000010000, "type": 3, "data": {"source": 0}},
                        {"timestamp": 1600000030000, "type": 3, "data": {"source": 0}},
                    ]
                },
            )
            self.assertEqual(recording["has_next"], False)

    def test_get_snapshots_does_not_leak_teams(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            another_team = Team.objects.create(organization=self.organization)
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user1",
                session_id="1",
                timestamp=now() + relativedelta(seconds=10),
                team_id=another_team.pk,
                data={"source": "other team"},
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user2",
                session_id="1",
                timestamp=now(),
                team_id=self.team.id,
                data={"source": 0},
            )

            filter = create_recording_filter("1")
            recording: DecompressedRecordingData = SessionRecordingEvents(
                team=self.team, session_recording_id="1"
            ).get_snapshots(filter.limit, filter.offset)

            self.assertEqual(
                recording["snapshot_data_by_window_id"],
                {"": [{"data": {"source": 0}, "timestamp": 1600000000000, "type": 3}]},
            )

    def test_get_snapshots_with_no_such_session(self):
        filter = create_recording_filter("xxx")
        recording: DecompressedRecordingData = SessionRecordingEvents(
            team=self.team, session_recording_id="xxx"
        ).get_snapshots(filter.limit, filter.offset)
        assert not recording

    def test_get_chunked_snapshots(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            chunked_session_id = "7"
            snapshots_per_chunk = 2
            limit = 20
            for _ in range(30):
                create_snapshots(
                    snapshot_count=snapshots_per_chunk,
                    distinct_id="user",
                    session_id=chunked_session_id,
                    timestamp=now(),
                    team_id=self.team.id,
                )

            filter = create_recording_filter(chunked_session_id)
            recording: DecompressedRecordingData = SessionRecordingEvents(
                team=self.team, session_recording_id=chunked_session_id
            ).get_snapshots(limit, filter.offset)
            self.assertEqual(len(recording["snapshot_data_by_window_id"][""]), limit * snapshots_per_chunk)
            self.assertTrue(recording["has_next"])

    def test_get_chunked_snapshots_with_specific_limit_and_offset(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            chunked_session_id = "7"
            limit = 10
            offset = 5
            snapshots_per_chunk = 2
            for index in range(16):
                create_snapshots(
                    snapshot_count=snapshots_per_chunk,
                    distinct_id="user",
                    session_id=chunked_session_id,
                    timestamp=now() + relativedelta(minutes=index),
                    team_id=self.team.id,
                )

            filter = create_recording_filter(chunked_session_id, limit, offset)
            recording: DecompressedRecordingData = SessionRecordingEvents(
                team=self.team, session_recording_id=chunked_session_id
            ).get_snapshots(limit, filter.offset)

            self.assertEqual(len(recording["snapshot_data_by_window_id"][""]), limit * snapshots_per_chunk)
            self.assertEqual(recording["snapshot_data_by_window_id"][""][0]["timestamp"], 1_600_000_300_000)
            self.assertTrue(recording["has_next"])

    def test_get_metadata(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            timestamp = now()
            create_snapshots(
                team_id=self.team.id,
                snapshot_count=1,
                distinct_id="u",
                session_id="1",
                timestamp=timestamp,
                window_id="1",
            )
            create_snapshots(
                team_id=self.team.id,
                snapshot_count=1,
                distinct_id="u",
                session_id="1",
                timestamp=timestamp + relativedelta(seconds=3),
                window_id="1",
                has_full_snapshot=False,
                source=3,
            )
            create_snapshots(
                team_id=self.team.id,
                snapshot_count=1,
                distinct_id="u",
                session_id="1",
                timestamp=timestamp + relativedelta(seconds=1),
                window_id="1",
                has_full_snapshot=False,
                source=3,
            )

            recording = SessionRecordingEvents(team=self.team, session_recording_id="1").get_metadata()

            self.assertEqual(
                recording,
                RecordingMetadata(
                    distinct_id="u",
                    duration=3,
                    click_count=0,
                    keypress_count=0,
                    urls=[],
                    start_time=now(),
                    end_time=now() + relativedelta(seconds=3),
                ),
            )

    def test_get_metadata_for_non_existant_session_id(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            recording = SessionRecordingEvents(team=self.team, session_recording_id="1").get_metadata()
            self.assertEqual(recording, None)

    def test_get_metadata_does_not_leak_teams(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            another_team = Team.objects.create(organization=self.organization)
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now(),
                team_id=another_team.pk,
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now() + relativedelta(seconds=10),
                team_id=self.team.id,
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now() + relativedelta(seconds=20),
                team_id=self.team.id,
            )
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now() + relativedelta(seconds=30),
                team_id=self.team.id,
            )

            recording = SessionRecordingEvents(team=self.team, session_recording_id="1").get_metadata()
            assert recording is not None
            assert recording["start_time"] != now()

    def test_get_snapshots_with_date_filter(self):
        with freeze_time("2020-09-13T12:26:40.000Z"):
            # This snapshot should be filtered out
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now() - relativedelta(days=2),
                team_id=self.team.id,
            )
            # This snapshot should appear
            create_snapshot(
                has_full_snapshot=False,
                distinct_id="user",
                session_id="1",
                timestamp=now(),
                team_id=self.team.id,
            )

            filter = create_recording_filter(
                "1",
            )
            recording: DecompressedRecordingData = SessionRecordingEvents(
                team=self.team, session_recording_id="1", recording_start_time=now()
            ).get_snapshots(filter.limit, filter.offset)

            self.assertEqual(len(recording["snapshot_data_by_window_id"][""]), 1)

    def test_should_parse_metadata_efficiently(self):
        """
        We can end up with a lot of metadata events so it is important to see if any of our parsing slows things down at scale.
        """

        start_time = datetime(2023, 1, 1, 0, 0, tzinfo=timezone.utc)
        random_event_times = list(range(0, 100000))
        end_time = datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=len(random_event_times) - 1)

        # Create a bunch of mock events in the wrong order
        random.shuffle(random_event_times)
        start_timestamp = round(start_time.timestamp() * 1000)
        mock_events = [
            SessionRecordingEvent(
                session_id="18586b7d1d3c52-0d746e4c6fc6b3-17525635-384000-18586b7d1d4276e",
                window_id="18586b7d1d528f6-026e4b0f3a575c-17525635-384000-18586b7d1d6760",
                distinct_id="123456789123456789",
                timestamp=datetime(2023, 1, 1) - timedelta(seconds=x),
                events_summary=[
                    {"timestamp": start_timestamp + (x * 1000), "type": 2, "data": {}},
                    {"timestamp": start_timestamp + (x * 1000), "type": 3, "data": {"source": 0}},
                    {"timestamp": start_timestamp + (x * 1000), "type": 3, "data": {"source": 1}},
                    {"timestamp": start_timestamp + (x * 1000), "type": 3, "data": {"source": 0}},
                    {"timestamp": start_timestamp + (x * 1000), "type": 3, "data": {"source": 1}},
                    {"timestamp": start_timestamp + (x * 1000), "type": 3, "data": {"source": 0}},
                    {"timestamp": start_timestamp + (x * 1000), "type": 3, "data": {"source": 0}},
                ],
                snapshot_data={},
            )
            for x in random_event_times
        ]

        task = SessionRecordingEvents(team=self.team, session_recording_id="1", recording_start_time=now())

        time = datetime.now()
        with patch.object(task, "_query_recording_snapshots", return_value=mock_events):
            metadata = task.get_metadata()
            assert metadata == RecordingMetadata(
                click_count=0,
                keypress_count=0,
                duration=13599,
                start_time=start_time,
                end_time=end_time,
                distinct_id="123456789123456789",
                urls=[],
            )

        duration = datetime.now() - time
        print("Took " + str(duration.total_seconds()) + " seconds to parse metadata.")  # noqa

        assert duration < timedelta(seconds=5)
