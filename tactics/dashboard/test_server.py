"""Offline regression tests: no Slurm command or cluster connection is permitted."""
import datetime
import http.client
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    from dashboard import server
except ImportError:
    import server

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / 'dashx' / 'sacct_dash.psv'


def psv(**changes):
    fields = server.JOB_FIELDS.split(',')
    row = dict(zip(fields, [
        '1', 'example', 'short', 'COMPLETED', '01:00:00', '03:00:00', '8',
        '16Gn', '', 'cpu=8,mem=16G', 'c0001', '2026-10-31T08:47:05', 'Unknown']))
    row.update(changes)
    return '|'.join(fields) + '\n' + '|'.join(row[field] for field in fields) + '\n'


class ParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = server.parse_jobs(FIXTURE.read_text())
        cls.by_id = {r['jobid']: r for r in cls.rows}

    def test_real_cpu_allocation(self):
        row = self.by_id['41099062']
        self.assertEqual((row['resource_type'], row['alloc_cpus'], row['gpu_count']), ('CPU', 32, 0))
        self.assertEqual(row['req_mem'], '64Gn')
        self.assertIsNone(row['max_rss'])
        self.assertEqual(row['state_code'], 'CANCELLED')
        # A CPU job on a GPU-capable partition is still CPU only.
        self.assertEqual(self.by_id['41104687']['resource_type'], 'CPU')

    def test_real_gpu_no_model_guess(self):
        row = self.by_id['41104642']
        self.assertEqual((row['resource_type'], row['gpu_count']), ('GPU', 1))
        # Partition name alone never establishes a model; only per-node nvidia-smi evidence does.
        if row['nodes'] in server.node_gpu_evidence():
            self.assertTrue(row['gpu_model_source'].startswith('node probe'))
        else:
            self.assertIsNone(row['gpu_model'])
            self.assertIsNone(row['gpu_model_source'])
        self.assertEqual(row['elapsed_seconds'], 2)

    def test_real_timezone_and_unknown(self):
        row = self.by_id['41104642']
        self.assertEqual(row['start'], '2026-10-31T14:47:05+01:00')
        self.assertEqual(row['end'], '2026-10-31T14:47:07+01:00')
        self.assertIsNone(self.by_id['41105069']['end'])
        self.assertIsNone(self.by_id['41105069']['max_rss'])

    def test_dst_calendars_and_ambiguous_times(self):
        for value, expected in [
            ('2026-01-15T12:00:00', '2026-01-15T19:00:00+01:00'),
            ('2026-07-15T12:00:00', '2026-07-15T19:00:00+02:00'),
            ('2026-03-15T12:00:00', '2026-03-15T18:00:00+01:00'),
            ('2026-11-01T01:30:00-05:00', '2026-11-01T07:30:00+01:00'),
            ('2026-11-01T01:30:00-06:00', '2026-11-01T08:30:00+01:00'),
            ('2026-11-01T01:30:00', None),
            ('2026-03-08T02:30:00', None),
            ('Unknown', None), ('bad date', None), ('2026-10-31', None)
        ]:
            with self.subTest(value=value): self.assertEqual(server.job_time(value), expected)

    def test_eu_dst_boundaries_in_utc(self):
        for value, expected in [
            ('2026-03-29T00:59:59', '2026-03-29T01:59:59+01:00'),
            ('2026-03-29T01:00:00', '2026-03-29T03:00:00+02:00'),
            ('2026-10-25T00:59:59', '2026-10-25T02:59:59+02:00'),
            ('2026-10-25T01:00:00', '2026-10-25T02:00:00+01:00'),
            # A transition can fall on the last day of the month.
            ('2024-03-31T01:00:00Z', '2024-03-31T03:00:00+02:00'),
            ('2021-10-31T01:00:00Z', '2021-10-31T02:00:00+01:00'),
            ('2026-11-01T01:30:00', '2026-11-01T02:30:00+01:00'),
            ('2026-03-08T02:30:00', '2026-03-08T03:30:00+01:00')
        ]:
            with self.subTest(value=value):
                self.assertEqual(server.job_time(value, 'UTC'), expected)

    def test_us_dst_boundaries_in_local_time(self):
        for value, expected in [
            ('2026-03-08T01:59:59', '2026-03-08T08:59:59+01:00'),
            ('2026-03-08T02:00:00', None),
            ('2026-03-08T02:59:59.999999', None),
            ('2026-03-08T03:00:00', '2026-03-08T09:00:00+01:00'),
            ('2026-11-01T00:59:59', '2026-11-01T06:59:59+01:00'),
            ('2026-11-01T01:00:00', None),
            ('2026-11-01T01:59:59.999999', None),
            ('2026-11-01T02:00:00', '2026-11-01T09:00:00+01:00'),
            ('2024-03-10T02:30:00', None),
            ('2024-11-03T01:30:00', None)
        ]:
            with self.subTest(value=value):
                self.assertEqual(server.job_time(value), expected)
        row = server.parse_jobs(psv(Start='2026-11-01T01:30:00', End='2026-03-08T02:30:00'))[0]
        self.assertIsNone(json.loads(json.dumps(row))['start'])
        self.assertIsNone(row['end'])

    def test_manual_iso_parser(self):
        for value, expected in [
            ('2026-10-31T08:47:05Z', '2026-10-31T09:47:05+01:00'),
            ('2026-10-31 08:47:05.123456+00:00', '2026-10-31T09:47:05.123456+01:00'),
            ('2026-10-31T08:47:05.1-0500', '2026-10-31T14:47:05.100000+01:00'),
            ('2026-01-01T00:15:00+05:30', '2025-12-31T19:45:00+01:00'),
            ('2024-02-29T23:30:00-03:30', '2024-03-01T04:00:00+01:00')
        ]:
            with self.subTest(value=value):
                self.assertEqual(server.job_time(value), expected)
                self.assertEqual(server.job_time(value, 'UTC'), expected)
        for value in [
            '', 'Unknown', '2026-10-31', '2026-10-31T12:30', '2026-02-29T00:00:00',
            '2026-13-01T00:00:00', '2026-01-01T24:00:00', '2026-01-01T00:60:00',
            '2026-01-01T00:00:60', '2026-01-01T00:00:00+24:00', '2026-01-01T00:00:00-05:60',
            '2026-01-01T00:00:00junk', '2026-01-01T00:00:00.1234567Z',
            '0000-01-01T00:00:00', '0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59Z'
        ]:
            with self.subTest(value=value):
                self.assertIsNone(server.job_time(value))

    def test_legacy_history_iso(self):
        for value, expected in [
            ('2026-03-29T01:00:00', '2026-03-29T01:00:00+00:00'),
            ('2026-03-29T03:00:00+02:00', '2026-03-29T01:00:00+00:00'),
            ('Unknown', 'Unknown'), ('invalid', 'invalid')
        ]:
            self.assertEqual(server.slurm_end(value), expected)

    def test_gpu_types_and_no_double_count(self):
        for tres, partition, count, model, source in [
            ('cpu=8,gres/gpu=2,gres/gpu:a100=2', 'short', 2, 'a100', 'AllocTRES'),
            ('cpu=8,gres/gpu:h100=4', 'short', 4, 'h100', 'AllocTRES'),
            ('cpu=8,gres/gpu=2', 'gpu-a100', 2, 'A100', 'partition'),
            ('cpu=8,gres/gpu=1', 'amperenodes', 1, None, None),
            ('cpu=8,gres/gpu=1', 'amd-hdr100', 1, None, None),
            ('cpu=8,gres/gpu=3,gres/gpu:a100=1', 'short', 3, None, None),
            ('cpu=8,gres/gpu=2,gres/gpu:a100=1,gres/gpu:h100=1', 'short', 2, 'a100, h100', 'AllocTRES'),
            ('cpu=8', 'gpu-a100', 0, None, None),
            ('', 'gpu-a100', None, None, None),
            ('bad', 'short', None, None, None),
            ('cpu=8,gres/gpu=bad', 'gpu-a100', None, None, None)
        ]:
            with self.subTest(tres=tres): self.assertEqual(server.gpu_allocation(tres, partition), (count, model, source))

    def test_unknown_and_missing_fields(self):
        row=server.parse_jobs(psv(AllocCPUS='', AllocTRES='', Start='Unknown', Elapsed='Unknown', ReqMem='N/A', NodeList='None'))[0]
        for key in ['alloc_cpus','gpu_count','gpu_model','resource_type','start','end','elapsed_seconds','req_mem','nodes','max_rss']:
            self.assertIsNone(row[key], key)
        row=server.parse_jobs('JobID|JobName\n12|partial\n')[0]
        self.assertIsNone(row['partition'])
        self.assertIsNone(row['alloc_cpus'])
        self.assertEqual(server.parse_jobs(''), [])
        with self.assertRaises(ValueError): server.parse_jobs('garbage\nnot a job')

    def test_duration_and_steps(self):
        for s,n in [('1-02:03:04',93784),('125:00:00',450000),('03:04',184),('00:00:00',0),('UNLIMITED',None),('',None),('00:60:00',None)]:
            self.assertEqual(server.elapsed_seconds(s),n)
        header, row=psv().splitlines()
        parsed=server.parse_jobs(header+'|\n'+row+'|\n'+row.replace('1|example','1.batch|example')+'|\n'+row+'|\n')
        self.assertEqual(len(parsed),1)

    def test_real_resource_accounting(self):
        summary=server.job_summary(self.rows)
        self.assertEqual(summary['running'],2)
        raw=FIXTURE.read_text().splitlines()[1:]
        cpu=0;gpu=0
        for line in raw:
            cells=line.split('|');h,m,s=map(int,cells[4].split(':'));hours=h+m/60+s/3600
            cpu+=hours*int(cells[6])
            if 'gres/gpu=1' in cells[9]:gpu+=hours
        self.assertAlmostEqual(summary['cpu_hours'],cpu)
        self.assertAlmostEqual(summary['gpu_hours'],gpu)
        self.assertEqual(summary['total'],len(raw))
        self.assertEqual(sum(summary[k] for k in ['running','completed','failed','other']),len(raw))

    def test_partial_resource_usage(self):
        rows=server.parse_jobs(psv(AllocCPUS='',AllocTRES=''))
        summary=server.job_summary(rows)
        self.assertIsNone(summary['cpu_hours'])
        self.assertIsNone(summary['gpu_hours'])
        self.assertEqual(summary['cpu_missing_jobs'],1)
        self.assertIsNone(server.job_summary([],False)['completed'])
        self.assertEqual(server.job_summary([])['completed'],0)


class JobsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='.dash-test-',dir=ROOT)
        self.root=Path(self.tmp.name)
        (self.root/'status').mkdir()
        self.root_patch=patch.object(server,'ROOT',str(self.root));self.root_patch.start()
        self.env_patch=patch.dict(os.environ,{'USER':'test-user','DASH_OFFLINE':'0'});self.env_patch.start()
        server._JOBS_CACHE.update(at=0,data=None)
        self.addCleanup(self.tmp.cleanup);self.addCleanup(self.root_patch.stop);self.addCleanup(self.env_patch.stop)

    def test_exact_command_timeout_timezone_cache(self):
        with patch.object(server.subprocess,'check_output',return_value=psv().encode()) as command:
            first=server.jobs();second=server.jobs()
            self.assertIs(first,second);command.assert_called_once()
            args=command.call_args[0][0];kwargs=command.call_args[1]
            self.assertEqual(args[:4],['sacct','-u','test-user','-S'])
            self.assertEqual(args[5:],['-X','-P','-o',server.JOB_FIELDS])
            since=server.parse_iso(args[4])
            delta=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)-since
            self.assertAlmostEqual(delta.total_seconds(),3*86400,delta=3)
            self.assertEqual(kwargs['timeout'],10)
            self.assertEqual(kwargs['env']['TZ'],'UTC')
            self.assertEqual(kwargs['env']['SLURM_TIME_FORMAT'],'standard')
            self.assertEqual(first['source'],'sacct')
            self.assertEqual(first['source_timezone'],'UTC')
            self.assertEqual(first['timezone'],'Europe/Amsterdam')
            self.assertEqual(first['jobs'][0]['start'],'2026-10-31T09:47:05+01:00')
            self.assertIsNone(first['error'])
            server._JOBS_CACHE['at']-=61
            server.jobs();self.assertEqual(command.call_count,2)

    def test_unavailable_falls_back(self):
        (self.root/'status'/'jobs_cache.psv').write_text(FIXTURE.read_text())
        with patch.object(server.subprocess,'check_output',side_effect=FileNotFoundError('sacct')):
            data=server.jobs()
        self.assertEqual(data['source'],'status/jobs_cache.psv')
        self.assertEqual(data['source_timezone'],'America/Chicago')
        row = next(row for row in data['jobs'] if row['jobid'] == '41104642')
        self.assertEqual(row['start'],'2026-10-31T14:47:05+01:00')
        self.assertGreater(len(data['jobs']),0)
        self.assertIn('sacct',data['error'])
        self.assertIsNotNone(data['cache_file_updated'])

    def test_legacy_slurm_utc_query(self):
        def output(args, **kwargs):
            self.assertEqual(kwargs['env']['TZ'], 'UTC')
            self.assertEqual(kwargs['env']['SLURM_TIME_FORMAT'], 'standard')
            self.assertEqual(kwargs['timeout'], 15)
            if args[0] == 'sacct':
                since = server.parse_iso(args[args.index('-S') + 1])
                delta = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - since
                self.assertAlmostEqual(delta.total_seconds(), 2 * 86400, delta=3)
                return b'1|example|COMPLETED|01:00:00|2026-03-29T01:00:00|\n'
            self.assertEqual(args[0], 'squeue')
            return b''

        with patch.dict(server._SLURM_CACHE, {'at': 0, 'data': None}), \
                patch.dict(os.environ, {'TZ': 'America/Chicago', 'SLURM_TIME_FORMAT': 'relative'}), \
                patch.object(server.subprocess, 'check_output', side_effect=output) as command:
            data = server.slurm()
            self.assertEqual(command.call_count, 2)
            self.assertEqual(data['history'][0]['end'], '2026-03-29T01:00:00+00:00')
            self.assertEqual(os.environ['TZ'], 'America/Chicago')

    def test_timeout_no_cache_returns_empty_with_error(self):
        with patch.object(server.subprocess,'check_output',side_effect=subprocess.TimeoutExpired('sacct',10)):
            data=server.jobs()
        self.assertEqual(data['jobs'],[])
        self.assertIsNone(data['source'])
        self.assertIsNone(data['source_timezone'])
        self.assertIsNone(data['summary']['running'])
        self.assertIn('10s',data['error_en'])

    def test_offline_never_runs_slurm(self):
        with patch.dict(os.environ,{'DASH_OFFLINE':'1'}),patch.object(server.subprocess,'check_output',side_effect=AssertionError('Must not query cluster')) as command:
            data=server.jobs()
            result=server.command(['squeue'])
        command.assert_not_called()
        self.assertEqual(data['jobs'],[])
        self.assertIn('DASH_OFFLINE',result[1])

    def test_bad_and_escaping_fallback(self):
        cache=self.root/'status'/'jobs_cache.psv'
        cache.write_text('invalid')
        with patch.dict(os.environ,{'DASH_OFFLINE':'1'}):self.assertEqual(server.jobs()['jobs'],[])
        cache.unlink();cache.symlink_to(FIXTURE)
        server._JOBS_CACHE.update(at=0,data=None)
        with patch.dict(os.environ,{'DASH_OFFLINE':'1'}):self.assertIsNone(server.jobs()['source'])


class HttpSmokeTests(unittest.TestCase):
    def test_live_local_ideas_and_jobs(self):
        server._JOBS_CACHE.update(at=0,data=None)
        with patch.dict(os.environ,{'DASH_OFFLINE':'1'}),patch.object(server.subprocess,'check_output',side_effect=AssertionError('No cluster access')):
            httpd=server.Server(('127.0.0.1',0),server.Handler)
            thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
            try:
                for path in ['/api/ideas','/api/jobs','/api/highlights','/api/slurm','/','/app.js','/style.css']:
                    with self.subTest(path=path):
                        conn=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
                        conn.request('GET',path);response=conn.getresponse();raw=response.read();conn.close()
                        self.assertEqual(response.status,200)
                        if path=='/api/ideas':self.assertEqual(json.loads(raw),json.loads((ROOT/'status'/'ideas.json').read_text(encoding='utf-8')))
                        if path=='/api/jobs':
                            self.assertIn('jobs',json.loads(raw));self.assertIn('summary',json.loads(raw))
            finally:
                httpd.shutdown();httpd.server_close();thread.join()


if __name__=='__main__':
    unittest.main()
