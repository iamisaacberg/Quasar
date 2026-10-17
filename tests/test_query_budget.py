"""Offline quota accounting: completed scans, running reservations, incomplete history."""
import json
import subprocess
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from quasar.adapters.query_budget import audit,reservation,CEILING

NOW=datetime(2026,10,17,tzinfo=timezone.utc)


class QueryBudgetTests(unittest.TestCase):
    def test_completed_bytes_and_running_caps_are_reserved(self):
        self.assertEqual(reservation({'configuration':{'query':{}},'status':{'state':'DONE'},'statistics':{'query':{'totalBytesBilled':'123','totalBytesProcessed':'120'}}}),123)
        self.assertEqual(reservation({'configuration':{'query':{'maximumBytesBilled':'500'}},'status':{'state':'RUNNING'}}),500)
        self.assertGreater(reservation({'configuration':{'query':{}},'status':{'state':'RUNNING'}}),CEILING)
        self.assertEqual(reservation({'configuration':{'query':{}},'status':{'state':'DONE','errorResult':{'reason':'bytesBilledLimitExceeded'}}}),0)

    @patch('quasar.adapters.query_budget.subprocess.run')
    def test_month_filter_and_project_wide_job_inventory(self,run):
        listing=[{'jobReference':{'jobId':'new'},'statistics':{'creationTime':str(int(NOW.timestamp()*1000))}},
                 {'jobReference':{'jobId':'old'},'statistics':{'creationTime':'1'}}]
        job={'configuration':{'query':{}},'status':{'state':'DONE'},'statistics':{'query':{'totalBytesBilled':'300'}}}
        run.side_effect=[subprocess.CompletedProcess([],0,json.dumps(listing)),subprocess.CompletedProcess([],0,json.dumps(job))]
        result=audit('test-project',now=NOW)
        self.assertEqual(result['bytes_reserved_or_billed'],300)
        self.assertEqual(len(result['jobs']),1)
        self.assertIn('-a',run.call_args_list[0].args[0])

    @patch('quasar.adapters.query_budget.subprocess.run')
    def test_truncated_job_history_fails_closed(self,run):
        run.return_value=subprocess.CompletedProcess([],0,json.dumps([{}]*1000))
        with self.assertRaises(ValueError):audit('test-project',now=NOW)
