import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from flask import Flask
from test_preparation import isolated_backend


class ProgressTrackingTests(unittest.TestCase):
    def setUp(self):
        self.backend = isolated_backend()
        self.app = Flask(__name__)
        self.data = self.backend['default_data']()
        self.topic = {'id': 'topic', 'name': 'Topic', 'status': 'not-started',
                      'estimatedHours': None, 'roi': None, 'examType': 'both',
                      'activeStages': ['R1'], 'startDate': None, 'completionDate': None}
        self.data['subjects'] = [{'id': 'subject', 'name': 'Subject', 'color': '#123456',
                                 'topics': [self.topic]}]
        self.saved = []
        self.backend['load_data'] = lambda: self.data
        self.backend['save_data'] = lambda data: self.saved.append(copy.deepcopy(data))
        self.now = datetime(2026, 10, 21, 8, tzinfo=timezone.utc).timestamp()

    def call(self, name, body=None, topic_id='topic'):
        with self.app.test_request_context(method='POST', json=body or {}):
            return self.backend[name]('subject') if name == 'api_add_topic' else self.backend[name]('subject', topic_id)

    def test_new_topic_has_blank_fields_even_with_completed_subject_history(self):
        self.topic.update(status='completed', estimatedHours=20, completionDate='2026-10-20')
        with self.app.test_request_context(method='POST', json={'name': 'New topic'}):
            result = self.backend['api_add_topic']('subject').get_json()
        self.assertIsNone(result['estimatedHours'])
        self.assertIsNone(result['roi'])
        self.assertEqual(result['learningSeconds'], 0)

    def test_optional_fields_can_be_set_and_cleared(self):
        for body in ({'estimatedHours': 0.25, 'roi': 'high'}, {'estimatedHours': None, 'roi': None}):
            with self.app.test_request_context(method='PUT', json=body):
                result = self.backend['api_edit_topic']('subject', 'topic')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.topic['estimatedHours'], body['estimatedHours'])
            self.assertEqual(self.topic['roi'], body['roi'])

    def test_invalid_duration_is_rejected_without_changes(self):
        for value in (-1, 0, True, 'bad', 101, float('inf')):
            with self.subTest(value=value):
                response, status = self.call('api_add_topic', {'name': 'Bad', 'estimatedHours': value})
                self.assertEqual(status, 400)
                self.assertIn('Duration', response.get_json()['error'])
        self.assertEqual(len(self.data['subjects'][0]['topics']), 1)
        self.assertFalse(self.saved)

    def test_start_pause_resume_finish_tracks_actual_time_once(self):
        with patch('time.time', return_value=self.now):
            self.call('api_start_topic')
            started = self.topic['timerStartedAt']
            self.call('api_start_topic')
        self.assertEqual(self.topic['timerStartedAt'], started)
        with patch('time.time', return_value=self.now + 900):
            self.call('api_pause_topic')
            self.call('api_pause_topic')
        self.assertAlmostEqual(self.backend['get_actual_hours'](self.data, 'topic'), .25)
        self.assertEqual(len(self.data['studyLogs']), 1)
        with patch('time.time', return_value=self.now + 1200):
            self.call('api_start_topic')
        with patch('time.time', return_value=self.now + 2100):
            result = self.call('api_complete_topic').get_json()
            self.call('api_complete_topic')
        self.assertEqual(self.topic['learningSeconds'], 1800)
        self.assertAlmostEqual(self.backend['get_actual_hours'](self.data, 'topic'), .5)
        self.assertIsNone(self.topic['estimatedHours'])
        self.assertIsNone(self.topic['timerStartedAt'])
        self.assertEqual(self.topic['status'], 'completed')
        self.assertIn('r1', result['schedule'])
        self.assertEqual(len(self.data['studyLogs']), 2)

    def test_switching_topics_pauses_previous_timer(self):
        second = {**self.topic, 'id': 'second', 'name': 'Second'}
        self.data['subjects'][0]['topics'].append(second)
        with patch('time.time', return_value=self.now):
            self.call('api_start_topic')
        with patch('time.time', return_value=self.now + 600):
            self.call('api_start_topic', topic_id='second')
        self.assertIsNone(self.topic['timerStartedAt'])
        self.assertIsNotNone(second['timerStartedAt'])
        self.assertEqual(self.topic['status'], 'learning')
        self.assertEqual(self.topic['learningSeconds'], 600)

    def test_midnight_timer_logs_on_each_ist_date(self):
        start = datetime.fromisoformat('2026-10-20T23:30:00+05:30').timestamp()
        with patch('time.time', return_value=start):
            self.call('api_start_topic')
        with patch('time.time', return_value=start + 3600):
            self.call('api_pause_topic')
        self.assertEqual([(log['date'], log['hours']) for log in self.data['studyLogs']],
                         [('2026-10-20', .5), ('2026-10-21', .5)])

    def test_unknown_duration_detail_and_live_time_are_supported(self):
        with patch('time.time', return_value=self.now):
            self.call('api_start_topic')
        with patch('time.time', return_value=self.now + 3600):
            result = self.call('api_topic_detail').get_json()
        self.assertIsNone(result['remainingHours'])
        self.assertEqual(result['actualHours'], 1)
        self.assertEqual(self.data['studyLogs'], [])
        self.assertIsNotNone(self.topic['timerStartedAt'])

    def test_migration_clears_only_untouched_automatic_metadata(self):
        self.data.pop('progressTrackingVersion')
        self.topic.update(estimatedHours=7.5, roi='medium', estimateSource='initial-planning-default',
                          revisionSchedule={'r1': {'date': '2028-01-01'}})
        started = {**self.topic, 'id': 'started', 'status': 'learning', 'startDate': '2026-10-20'}
        manual = {**self.topic, 'id': 'manual', 'estimateSource': 'user-estimate', 'roiSource': 'user'}
        self.data['subjects'][0]['topics'].extend([started, manual])
        self.assertTrue(self.backend['_migrate_data'](self.data))
        self.assertIsNone(self.topic['estimatedHours'])
        self.assertIsNone(self.topic['roi'])
        self.assertNotIn('revisionSchedule', self.topic)
        self.assertEqual(started['estimatedHours'], 7.5)
        self.assertEqual(manual['estimatedHours'], 7.5)
        self.assertEqual(manual['roi'], 'medium')
        self.assertFalse(self.backend['_migrate_data'](self.data))

    def test_migration_preserves_recorded_progress_on_unstarted_topic(self):
        self.data.pop('progressTrackingVersion')
        self.topic.update(estimatedHours=7.5, roi='medium')
        self.data['studyLogs'] = [{'topicId': 'topic', 'hours': 1, 'date': '2026-10-20'}]
        self.backend['_migrate_data'](self.data)
        self.assertEqual(self.topic['estimatedHours'], 7.5)
        self.assertEqual(len(self.data['studyLogs']), 1)

    def test_unstarted_topic_cannot_be_finished(self):
        _, status = self.call('api_complete_topic')
        self.assertEqual(status, 409)
        self.assertFalse(self.saved)

    def test_unearned_stage_cannot_be_marked_done(self):
        self.topic.update(status='completed', completionDate='2026-10-20', activeStages=['R1', 'R3'])
        with self.app.test_request_context(method='POST', json={'topicId': 'topic', 'type': 'R3'}):
            response, status = self.backend['api_mark_revision']()
        self.assertEqual(status, 409)
        self.assertIn('prerequisite', response.get_json()['error'])
        self.assertEqual(self.data['completedRevisions'], {})

    def test_reset_clears_timer_and_logs(self):
        self.topic.update(status='learning', timerStartedAt='2026-10-20T00:00:00+00:00', learningSeconds=100)
        self.call('api_reset_topic')
        self.assertIsNone(self.topic['timerStartedAt'])
        self.assertEqual(self.topic['learningSeconds'], 0)
        self.assertEqual(self.data['studyLogs'], [])

    def test_related_links_are_bidirectional_and_self_links_rejected(self):
        other = {**self.topic, 'id': 'other', 'relatedTopicIds': []}
        self.data['subjects'][0]['topics'].append(other)
        self.call('api_add_related', {'relatedTopicId': 'other'})
        self.assertEqual(self.topic['relatedTopicIds'], ['other'])
        self.assertEqual(other['relatedTopicIds'], ['topic'])
        _, status = self.call('api_add_related', {'relatedTopicId': 'topic'})
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
