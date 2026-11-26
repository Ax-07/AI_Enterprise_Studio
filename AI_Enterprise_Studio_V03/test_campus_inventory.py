"""O05.1: reconcile the static campus registry with the historical inventory."""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class CampusInventoryTests(unittest.TestCase):
    def test_registry_and_inventory(self):
        layout=(ROOT/'interface/live-layout.js').read_text(encoding='utf-8')
        layout=json.loads(layout[layout.index('['):layout.rindex(']')+1])
        modules=(ROOT/'interface/live-modules.js').read_text(encoding='utf-8')
        legacy=json.loads(modules.split('stations:Object.freeze(',1)[1].split('), native:',1)[0])
        native=json.loads(modules.split('native:Object.freeze(',1)[1].split(')});',1)[0])
        expected={'ATLAS':(9,45,32),'ORION':(3,15,10),'NEXUS':(5,25,19),
            'MIDAS':(4,20,14),'HERMES':(8,40,32),'SENTINEL':(3,15,10),'CORE':(5,25,18)}
        self.assertEqual(len(layout),7)
        self.assertEqual({b['id'] for b in layout},set(expected))
        floors=[f for b in layout for f in b['floors']]
        self.assertEqual(len(floors),37)
        self.assertEqual(len({f['id'] for f in floors}),37)
        self.assertTrue(all(len(f['stations'])==5 for f in floors))
        ids=[st['id'] for f in floors for st in f['stations']]
        self.assertEqual(len(ids),185)
        self.assertEqual(len(set(ids)),185)
        linked=set(legacy)|set(native)
        self.assertEqual((len(legacy),len(native),len(set(legacy)&set(native))), (114,71,50))
        self.assertEqual(len(linked),135)
        self.assertLessEqual(linked,set(ids))
        for b in layout:
            stations=[s['id'] for f in b['floors'] for s in f['stations']]
            self.assertEqual((len(b['floors']),len(stations),len(set(stations)&linked)),expected[b['id']])
            for f in b['floors']:
                for i,st in enumerate(f['stations']):
                    self.assertEqual(st['id'],f['id']+':station:'+str(i))
                    self.assertTrue(st['destination'])
        inventory=(ROOT/'CAMPUS_CAPABILITIES.md').read_text(encoding='utf-8')
        entries=re.findall(r'^\| `([^ `]+:station:[0-4])` \|',inventory,re.M)
        self.assertEqual(len(entries),52)
        self.assertEqual(len(set(entries)),52)
        self.assertEqual(set(entries)&linked,{'PEOPLE17:station:0','COMMS:station:0'})
        self.assertEqual(set(entries)-linked,set(ids)-linked)
        self.assertEqual(len(set(ids)-linked),50)
