from app.query import normalize_query


def test_expands_recurring_payment_and_account_change() -> None:
    result = normalize_query(
        "매달 빠져나가는 금액을 다른 통장에서 나가게 하고 싶어요."
    )

    assert result.added_terms == ("자동이체", "자동납부", "출금계좌", "변경")
    assert result.rule_ids == ("QUERY-AUTO-001", "QUERY-AUTO-002")
    assert result.expanded.endswith("자동이체 자동납부 출금계좌 변경")


def test_keeps_direct_financial_term_without_duplicate_expansion() -> None:
    result = normalize_query("자동이체 조회")

    assert result.expanded == "자동이체 조회"
    assert result.added_terms == ()
    assert result.rule_ids == ()


def test_expands_early_loan_repayment_expression() -> None:
    result = normalize_query("대출을 일찍 갚을 때 수수료가 있나요?")

    assert result.added_terms == ("중도상환",)
    assert result.rule_ids == ("QUERY-LOAN-001",)
