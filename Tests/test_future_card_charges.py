import unittest
from datetime import date
from monthly_summary import future_card_charges, future_card_schedule


class FutureCardChargesTests(unittest.TestCase):
    def test_user_correction_keeps_november_and_december_is_second_parcel(self):
        from billing import apply_installment_adjustments
        adjustment=dict(description='IPG*123VIAGENS',amount='615.03',currency='BRL',
                        first_due_month='2026-11-01',installments=5,purchase_date='2026-09-28')
        card=dict(id=1,kind='cards',name='Cartão',due_date=date(2026,11,5),installment_adjustments=[adjustment])
        first=dict(id='original',description='IPG*123VIAGENS',amount='615.03',currency='BRL',installment=1,installments=5)
        november=apply_installment_adjustments(card,[first],date(2026,11,5))
        self.assertEqual(len(november),1)
        self.assertEqual(november[0]['id'],'original')
        self.assertEqual(apply_installment_adjustments(card,[],date(2026,11,5)),[])
        december=apply_installment_adjustments(card,[],date(2026,12,5))
        self.assertEqual(december[0]['installment'],2)
        self.assertTrue(december[0]['manual_adjustment'])
        self.assertEqual(len(apply_installment_adjustments(card,december,date(2026,12,5))),1)
        periods=[dict(card_id=1,previous_closing_date=date(2026,9,20),closing_date=date(2026,10,20),transactions=[first])]
        result=future_card_schedule([card],periods,[],date(2026,11,1))
        self.assertEqual([m['amount'] for m in result],['615.03']*4+[None,None])
        self.assertEqual([m['details'][0]['projected_installments'][0]['installment'] for m in result[:4]],[2,3,4,5])
    def test_six_month_schedule_crosses_year_without_repeating_cycles(self):
        cards=[dict(id=1,kind='cards',name='Cartão')]
        cycles=[dict(card_id=1,reference_month=date(2026,11,1),previous_closing_date=date(2026,10,20),
                     closing_date=date(2026,11,20),due_date=date(2026,12,5))]
        monthly=[dict(card_id=1,month=date(2026,11,1),transactions=[dict(amount='100',currency='BRL',installment=2,installments=12)])]
        result=future_card_schedule(cards,[],monthly,date(2026,11,1),cycles)
        self.assertEqual([m['month'] for m in result],['2026-12','2027-01','2027-02','2027-03','2027-04','2027-05'])
        self.assertEqual(result[0]['amount'],'100')
        self.assertTrue(all(m['amount'] == '100' and m['estimated'] for m in result[1:]))

    def test_remaining_parcels_stop_and_imported_installment_is_not_doubled(self):
        cards=[dict(id=1,kind='cards',name='Cartão',due_date=date(2026,11,5))]
        cycles=[dict(card_id=1,reference_month=date(2026,10,1),previous_closing_date=date(2026,9,20),closing_date=date(2026,10,20),due_date=date(2026,11,5)),
                dict(card_id=1,reference_month=date(2026,11,1),previous_closing_date=date(2026,10,20),closing_date=date(2026,11,20),due_date=date(2026,12,5))]
        rows=[dict(card_id=1,month=date(2026,10,1),transactions=[dict(id='p2',description='Compra',amount='50',currency='BRL',installment=2,installments=4)]),
              dict(card_id=1,month=date(2026,11,1),transactions=[dict(id='p3',description='Compra',amount='50',currency='BRL',installment=3,installments=4),dict(id='other',description='À vista',amount='20',currency='BRL')])]
        result=future_card_schedule(cards,[],rows,date(2026,11,1),cycles)
        self.assertEqual(result[0]['amount'],'70')
        self.assertEqual(result[0]['projected_amount'],'0')
        self.assertEqual(result[1]['amount'],'50')
        self.assertEqual(result[1]['details'][0]['projected_installments'][0]['installment'],4)
        self.assertIsNone(result[2]['amount'])

    def test_identical_separate_purchases_are_preserved_and_caches_deduplicated(self):
        cards=[dict(id=1,kind='cards',name='Cartão',due_date=date(2026,11,5))]
        tx=[dict(id=str(i),description='Loja',amount='25',currency='BRL',installment=1,installments=2) for i in range(2)]
        periods=[dict(card_id=1,previous_closing_date=date(2026,9,20),closing_date=date(2026,10,20),transactions=tx),
                 dict(card_id=1,previous_closing_date=date(2026,10,20),closing_date=date(2026,11,20),transactions=tx)]
        result=future_card_schedule(cards,periods,[],date(2026,11,1))
        self.assertEqual(result[0]['amount'],'50')
        self.assertEqual(result[0]['projected_amount'],'0')
        self.assertIsNone(result[1]['amount'])

    def test_description_installments_and_invalid_metadata(self):
        cards=[dict(id=1,kind='cards',name='Cartão',due_date=date(2026,11,5))]
        tx=[dict(id='ok',description='Loja PARC 02/03',amount='10',currency='BRL'),
            dict(id='date',description='Compra 03/11',amount='30',currency='BRL'),
            dict(id='bad',description='Outra',amount='20',currency='BRL',installment=0,installments=5),
            dict(id='credit',description='Estorno',amount='-10',currency='BRL',installment=1,installments=5)]
        periods=[dict(card_id=1,previous_closing_date=date(2026,9,20),closing_date=date(2026,10,20),transactions=tx)]
        result=future_card_schedule(cards,periods,[],date(2026,11,1))
        self.assertEqual(result[0]['amount'],'10')
        self.assertIsNone(result[1]['amount'])

    def test_future_pending_purchase_in_old_cache_does_not_shift_installments(self):
        cards=[dict(id=1,kind='cards',name='Cartão',due_date=date(2026,11,5))]
        tx=[dict(id='purchase',description='Loja',date='2026-11-10',status='PENDING',amount='25',currency='BRL',installment=1,installments=2)]
        periods=[dict(card_id=1,previous_closing_date=date(2026,9,20),closing_date=date(2026,10,20),transactions=tx),
                 dict(card_id=1,previous_closing_date=date(2026,10,20),closing_date=date(2026,11,20),transactions=tx)]
        result=future_card_schedule(cards,periods,[],date(2026,11,1))
        self.assertEqual(result[0]['projected_amount'],'0')
        self.assertEqual(result[1]['amount'],'25')
        self.assertIsNone(result[2]['amount'])

    def test_explicit_cycle_precedes_same_parcel_in_official_month_cache(self):
        cards=[dict(id=1,kind='cards',name='Cartão',due_date=date(2026,11,5))]
        tx=[dict(id='purchase',description='Loja',date='2026-11-01',status='PENDING',amount='25',currency='BRL',installment=1,installments=2)]
        rows=[dict(card_id=1,month=date(2026,11,1),transactions=tx,bills=[dict(due_date='2026-11-05')])]
        periods=[dict(card_id=1,previous_closing_date=date(2026,10,20),closing_date=date(2026,11,20),transactions=tx)]
        result=future_card_schedule(cards,periods,rows,date(2026,11,1))
        self.assertEqual(result[0]['amount'],'25')
        self.assertEqual(result[1]['amount'],'25')
        self.assertIsNone(result[2]['amount'])

    def test_selects_cycle_by_due_date_not_reference_month(self):
        cards=[dict(id=1,kind="cards",name="Bradesco",due_date=date(2026,11,5))]
        cycles=[dict(card_id=1,reference_month=date(2026,11,1),
                     previous_closing_date=date(2026,10,23),closing_date=date(2026,11,25),due_date=date(2026,12,5))]
        rows=[dict(card_id=1,month=date(2026,11,1),transactions=[dict(amount="2824.19",currency="BRL")]),
              dict(card_id=1,month=date(2026,12,1),transactions=[])]
        periods=[dict(card_id=1,previous_closing_date=date(2026,10,25),closing_date=date(2026,11,25),
                      transactions=[dict(amount="1858.03",currency="BRL")])]
        result=future_card_charges(cards,periods,rows,date(2026,11,1),cycles)
        self.assertEqual(result["amount"],"2824.19")
        self.assertEqual(result["details"][0]["due_date"],"2026-12-05")
        # Em dezembro, não repete a fatura que venceu em dezembro.
        january=future_card_charges(cards,periods,rows,date(2026,12,1),cycles)
        self.assertEqual(january["month"],"2027-01")
        self.assertIsNone(january["amount"])

    def test_january_installment_only_not_entire_purchase_or_december(self):
        cards=[dict(id=1,kind="cards",name="Cartão")]
        cycles=[dict(card_id=1,reference_month=date(2026,12,1),
                     previous_closing_date=date(2026,11,20),closing_date=date(2026,12,20),due_date=date(2027,1,5))]
        rows=[dict(card_id=1,month=date(2026,12,1),transactions=[
            dict(id="installment",amount="100",currency="BRL",installment=3,installments=12),
            dict(id="payment",amount="-500",currency="BRL",operation_type="PAGAMENTO_FATURA"),
            dict(id="refund",amount="-10",currency="BRL",operation_type="ESTORNO")])]
        result=future_card_charges(cards,[],rows,date(2026,12,1),cycles)
        self.assertEqual(result["amount"],"100")
        self.assertEqual(result["details"][0]["due_date"],"2027-01-05")

    def test_sums_different_closing_cycles_with_same_due_month(self):
        cards=[dict(id=i,kind="cards",name=str(i),due_date=date(2026,11,day)) for i,day in [(1,5),(2,10)]]
        periods=[dict(card_id=1,previous_closing_date=date(2026,10,25),closing_date=date(2026,11,25),transactions=[dict(amount="150",currency="BRL")]),
                 dict(card_id=2,previous_closing_date=date(2026,11,5),closing_date=date(2026,12,5),transactions=[dict(amount="50",currency="BRL")])]
        result=future_card_charges(cards,periods,[],date(2026,11,1))
        self.assertEqual(result["amount"],"200")
        self.assertFalse(result["partial"])

    def test_missing_cycle_and_empty_cache_is_unknown_not_zero(self):
        result=future_card_charges([dict(id=1,kind="cards",name="Card")],[],
            [dict(card_id=1,month=date(2027,1,1),transactions=[],bills=[])],date(2026,12,1))
        self.assertIsNone(result["amount"])
        self.assertTrue(result["partial"])

    def test_confirmed_empty_cycle_is_zero_and_missing_card_is_partial(self):
        cards=[dict(id=i,kind="cards",name=str(i)) for i in (1,2)]
        rows=[dict(card_id=1,month=date(2027,1,1),transactions=[],bills=[dict(due_date="2027-01-05")])]
        result=future_card_charges(cards,[],rows,date(2026,12,1))
        self.assertEqual(result["amount"],"0")
        self.assertEqual(result["missing_cards"],["2"])

    def test_old_due_month_before_closing_is_normalized_without_mutation(self):
        cycle=dict(card_id=1,reference_month=date(2026,11,1),previous_closing_date=date(2026,10,23),
                   closing_date=date(2026,11,25),due_date=date(2026,11,5))
        rows=[dict(card_id=1,month=date(2026,11,1),transactions=[dict(amount="25",currency="BRL")])]
        result=future_card_charges([dict(id=1,kind="cards",name="Card")],[],rows,date(2026,11,1),[cycle])
        self.assertEqual(result["amount"],"25")
        self.assertEqual(result["details"][0]["due_date"],"2026-12-05")
        self.assertEqual(cycle["due_date"],date(2026,11,5))


if __name__=="__main__":unittest.main()
