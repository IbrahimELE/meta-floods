"""Offline tests for evaluation correctness; no paid calls."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from common import classification, truth, distance_km, percentile, Ledger, CostLimit
from make_splits import flight, enriched, read_csv, ROOT

class MetricsTests(unittest.TestCase):
    def test_confusion_includes_failed_requests(self):
        records = [dict(truth={'flooding_any':y},prediction=p) for y,p in [(1,{'flooding_any':True}),(1,None),(0,{'flooding_any':True}),(0,{'flooding_any':False})]]
        with patch('common.CLASSES',('flooding_any',)):
            result = classification(records)
        m = result['per_class']['flooding_any']
        self.assertEqual((m['tp'],m['fp'],m['fn'],m['tn']),(1,1,1,1))
        self.assertEqual(m['f1'],.5)
        self.assertIsNone(result['macro_f1'])

    def test_label_unions(self):
        row = {k:'0' for k in ('flooding_any','flooding_structures','roads_damage','debris_any','buildings_affected','buildings_minor','buildings_major','buildings_destroyed')}
        row['buildings_destroyed']='1'
        self.assertEqual(truth(row)['buildings_affected_or_greater'],1)
        self.assertEqual(truth(row)['buildings_major_or_greater'],1)

    def test_geodesic_and_quantile(self):
        self.assertAlmostEqual(distance_km((0,0),(0,1)),111.195,places=2)
        self.assertEqual(distance_km((44,-72),(44,-72)),0)
        self.assertEqual(percentile([1,2,3,4],.5),2.5)

    def test_flight_exclusion_and_reproducibility(self):
        smoke = read_csv(ROOT/'samples/ladi_dev_set.csv')
        test = read_csv(ROOT/'eval/test_set.csv')
        self.assertEqual(len(test),100)
        self.assertEqual(len({r['url'] for r in test}),100)
        self.assertFalse({flight(r['url']) for r in smoke} & {flight(r['url']) for r in test})
        source = read_csv(ROOT/'data/eval/sources/ladi_v2_labels_test.csv')
        unique = {r['url']:r for r in source}
        excluded = {flight(r['url']) for r in smoke}
        eligible = [r for r in sorted(unique.values(),key=lambda r:r['url']) if flight(r['url']) not in excluded]
        self.assertEqual(enriched(eligible,100,42),test)

    def test_budget_survives_new_ledger_instance(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'eval') as folder, patch('common.DATA',Path(folder)):
            first = Ledger()
            first.reserve('test',8.9)
            second = Ledger()
            with self.assertRaises(CostLimit):
                second.reserve('test',.2)
            self.assertAlmostEqual(second.summary()['estimated_or_reserved_usd'],8.9)

if __name__ == '__main__':
    unittest.main()
