"""Source-link receipts must not claim full semantic verification."""
import copy
import unittest
from backend.provenance import digest, receipt


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.context={'snapshotDate':'2026-10-09','evidence':[
            {'id':'E1','text':'김치 리뷰 195건','source':'reviews.csv'},
            {'id':'E2','text':'매운맛 언급 38건','source':'reviews.csv'}]}
        self.result={'points':[{'text':'This is an interpretation.','evidenceIds':['E1','E2']}]}

    def test_counts_and_boundaries_are_independent_of_model_claims(self):
        result=receipt(self.context,self.result,'run-test','ask',True)
        self.assertEqual(result['linkedItemCount'],1)
        self.assertEqual(result['citedEvidenceCount'],2)
        self.assertEqual(result['evidenceCount'],2)
        self.assertEqual(result['checks']['semanticAccuracy'],'human_review_required')
        self.assertEqual(result['checks']['freshness'],'snapshot_only')
        self.assertEqual(len(result['evidenceDigest']),64)

    def test_unknown_or_repeated_or_absent_references_are_rejected(self):
        for refs in [['E9'],['E1','E1'],[]]:
            with self.subTest(refs=refs),self.assertRaises(ValueError):
                receipt(self.context,{'points':[{'evidenceIds':refs}]},'run','ask',True)

    def test_fingerprint_is_stable_across_key_order_but_tracks_changed_evidence(self):
        a={'id':'E1','text':'195'};b={'text':'195','id':'E1'}
        self.assertEqual(digest([a]),digest([b]))
        b['text']='196'
        self.assertNotEqual(digest([a]),digest([b]))

    def test_duplicate_source_identifiers_cannot_create_an_ambiguous_receipt(self):
        self.context['evidence'][1]['id']='E1'
        with self.assertRaises(ValueError):receipt(self.context,self.result,'run','ask',True)

    def test_unanswerable_questions_do_not_claim_citation_validation(self):
        self.context['evidence']=[]
        result=receipt(self.context,{'points':[]},'run','ask',False)
        self.assertFalse(result['generatedByAI'])
        self.assertEqual(result['checks']['sourceReferences'],'not_applicable')
        self.assertEqual(result['evidenceCount'],0)


if __name__=='__main__':unittest.main()
