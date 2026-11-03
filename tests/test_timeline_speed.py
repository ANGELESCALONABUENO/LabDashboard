import unittest
from unittest.mock import Mock
import timeline_speed as speed
class Response:
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self): return b'{}'
class SpeedTest(unittest.TestCase):
    def setUp(self):
        speed.USED.clear();speed.ESTIMATES.clear()
        self.now=1000
        self.ps={'state':'printing','filename':'test.gcode','total_duration':300,'print_duration':290}
        self.token=speed.ticket('SE01',self.ps,100,self.now*1000)
        self.reader=Mock(side_effect=lambda h,p: {'result':{'status':{'print_stats':self.ps,'gcode_move':{'speed_factor':.5 if p.endswith('?gcode_move') else 1}}}})
        self.opener=Mock(return_value=Response())
    def apply(self,percent,token=None):
        return speed.apply({'ticket':token or self.token,'percent':percent},self.reader,self.opener,lambda:self.now)
    def test_limits_and_duplicate(self):
        for percent in (5,200):
            token=speed.ticket('SE01',self.ps,100,self.now*1000)
            self.apply(percent,token)
        before=self.opener.call_count
        result=self.apply(50)
        self.assertTrue(result['confirmed'])
        self.assertEqual(self.apply(50),result)
        self.assertEqual(self.opener.call_count,before+1)
        self.assertEqual(self.opener.call_args.args[0].data,b'{"script": "M220 S50.00"}')
    def test_invalid_never_sends(self):
        for value in (4.99,200.01,float('nan'),float('inf'),True,'100',None):
            with self.assertRaises(ValueError):self.apply(value)
        self.opener.assert_not_called()
    def test_stopped_changed_job_and_speed(self):
        for change in ({'state':'complete'},{'filename':'other.gcode'},{'total_duration':0}):
            original=self.ps.copy();self.ps.update(change)
            with self.assertRaises(ValueError):self.apply(50)
            self.ps=original
        self.reader.return_value=None
        self.reader.side_effect=lambda h,p:{'result':{'status':{'print_stats':self.ps,'gcode_move':{'speed_factor':1.1}}}}
        with self.assertRaises(ValueError):self.apply(50)
        self.opener.assert_not_called()
    def test_expired_tampered_unknown_printer(self):
        self.now+=121
        with self.assertRaises(ValueError):self.apply(50)
        self.now=1000
        with self.assertRaises(ValueError):self.apply(50,self.token+'a')
        with self.assertRaises(ValueError):self.apply(50,speed.ticket('unknown',self.ps,100,self.now*1000))
        self.opener.assert_not_called()
    def test_restarted_job_with_same_filename(self):
        ps=dict(self.ps,_timeline_job_id='old-job')
        token=speed.ticket('SE01',ps,100,self.now*1000)
        original=self.reader.side_effect
        self.reader.side_effect=lambda h,p: {'result':{'jobs':[{'job_id':'new-job','status':'in_progress'}]}} if '/history/' in p else original(h,p)
        with self.assertRaises(ValueError):self.apply(50,token)
        self.opener.assert_not_called()
    def test_idex_uses_existing_bridge_only(self):
        import json
        token=speed.ticket('IDEX',self.ps,100,self.now*1000)
        with __import__('unittest').mock.patch.object(speed.time,'sleep'):
            result=self.apply(50,token)
        self.assertTrue(result['confirmed'])
        request=self.opener.call_args.args[0]
        self.assertEqual(request.full_url,'http://127.0.0.1:8811/api/command')
        self.assertEqual(json.loads(request.data),{'command':'M220 S50.00'})
        self.assertEqual(self.reader.call_args.args[0],'idex-bridge')
    def test_duet_conversion_and_stale_rejection(self):
        from datetime import datetime,timezone,timedelta
        data={'server_time':datetime.now(timezone.utc).isoformat(),'state':{'status':'processing'},'status':{'params':{'speedFactor':75}},'job':{'file':{'fileName':'0:/gcodes/test.gcode'},'duration':123}}
        result=speed.duet_status(data)['result']['status']
        self.assertEqual(result['gcode_move']['speed_factor'],.75)
        self.assertEqual(result['print_stats']['filename'],'test.gcode')
        self.assertEqual(result['print_stats']['state'],'printing')
        data['server_time']=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()
        with self.assertRaises(ValueError):speed.duet_status(data)
    def test_ambiguous_network_does_not_retry(self):
        self.opener.side_effect=TimeoutError
        self.assertFalse(self.apply(50)['confirmed'])
        self.apply(50)
        self.assertEqual(self.opener.call_count,1)
    def test_estimate_changes_then_uses_real_progress(self):
        ps=dict(self.ps)
        initial=speed.estimate('SE01',ps,.5,100,1000000)
        ps['total_duration']+=1
        slower=speed.estimate('SE01',ps,.5,50,1001000)
        self.assertAlmostEqual(slower,initial*2)
        ps['total_duration']+=40
        measured=speed.estimate('SE01',ps,.55,50,1041000)
        self.assertAlmostEqual(measured,360)
if __name__=='__main__':unittest.main()
