"""
Unit tests for shared_core modules:
- DataEngine normalization & accessible liquidity
- Causal FeatureEngineer
- ScamDetectionEngine mandatory safety gate
- OpportunityScorer (0-100) with missing/stale data penalties
- AdaptiveStrategyEngine (4 strategy families + NO_TRADE)
- PredictionEngine & WalkForwardValidator
"""
from __future__ import annotations

import unittest
import numpy as np

from backtesting.historical_data import HistoricalDatasetBuilder
from database.models import RiskClassification, StrategyFamily, TradeAction, TradeEligibility
from dex.liquidity_analyzer import LiquidityAnalyzer
from learning.model_training import ModelTrainer
from learning.walk_forward import WalkForwardValidator
from shared_core.data_engine import DataEngine
from shared_core.feature_engineering import FeatureEngineer
from shared_core.market_regime import MarketRegimeClassifier
from shared_core.opportunity_scoring import OpportunityScorer
from shared_core.prediction_engine import PredictionEngine
from shared_core.scam_detection import ScamDetectionEngine
from shared_core.sentiment_engine import SentimentEngine
from shared_core.smart_money import SmartMoneyEngine
from shared_core.strategy_engine import AdaptiveStrategyEngine


class TestSharedCore(unittest.TestCase):
    def setUp(self) -> None:
        self.timeline = HistoricalDatasetBuilder.build_multi_regime_dataset(num_steps=10)
        self.step_snaps = self.timeline[5]

    def test_accessible_liquidity_calculation(self) -> None:
        acc_locked = DataEngine.compute_accessible_liquidity(100000.0, lp_locked_pct=95.0, fee_bps=30)
        acc_unlocked = DataEngine.compute_accessible_liquidity(100000.0, lp_locked_pct=20.0, fee_bps=30)
        self.assertGreater(acc_locked, acc_unlocked)
        self.assertLessEqual(acc_locked, 50000.0)

    def test_scam_detection_mandatory_veto_overrides_opportunity(self) -> None:
        # Token index 3 in dataset is RUGTRAP (active mint + freeze authority, 84% top10 holders, 0 sells)
        scam_snap = self.step_snaps[3]
        scam_report = ScamDetectionEngine.evaluate(scam_snap, min_pool_liquidity_usd=15000.0)
        self.assertEqual(scam_report.classification, RiskClassification.CRITICAL_SCAM)
        self.assertEqual(scam_report.eligibility, TradeEligibility.REJECTED)
        self.assertGreaterEqual(scam_report.risk_score, 65.0)

        features = FeatureEngineer.extract_features(scam_snap)
        market_rep = MarketRegimeClassifier.classify(features, scam_snap.primary_pool.price_usd)
        sm_rep = SmartMoneyEngine.evaluate(scam_snap)
        sent_rep = SentimentEngine.evaluate(scam_snap)
        liq_rep = LiquidityAnalyzer.evaluate_pool(scam_snap.primary_pool)

        scorer = OpportunityScorer()
        opp = scorer.score(market_rep, sm_rep, sent_rep, liq_rep, scam_report, scam_snap.timestamp, scam_snap.timestamp)
        self.assertFalse(opp.is_eligible)

        ml_pred = PredictionEngine().predict_from_features(features)
        strat = AdaptiveStrategyEngine(min_opportunity_score=50.0).select_strategy(
            scam_snap.primary_pool.price_usd,
            features,
            market_rep,
            sm_rep,
            scam_report,
            opp,
            ml_pred,
        )
        self.assertEqual(strat.action, TradeAction.NO_TRADE)
        self.assertEqual(strat.strategy_family, StrategyFamily.NO_TRADE)

    def test_missing_data_penalized_not_rewarded(self) -> None:
        clean_snap = self.step_snaps[0]
        clean_snap.wallet_activity.data_available = False
        clean_snap.sentiment.data_available = False

        features = FeatureEngineer.extract_features(clean_snap)
        market_rep = MarketRegimeClassifier.classify(features, clean_snap.primary_pool.price_usd)
        sm_rep = SmartMoneyEngine.evaluate(clean_snap)
        sent_rep = SentimentEngine.evaluate(clean_snap)
        scam_rep = ScamDetectionEngine.evaluate(clean_snap)
        liq_rep = LiquidityAnalyzer.evaluate_pool(clean_snap.primary_pool)

        opp = OpportunityScorer().score(
            market_rep, sm_rep, sent_rep, liq_rep, scam_rep, clean_snap.timestamp, clean_snap.timestamp
        )
        self.assertEqual(opp.component_scores["smart_money"], 35.0)
        self.assertEqual(opp.component_scores["sentiment"], 35.0)
        self.assertGreaterEqual(len(opp.penalties_applied), 2)

    def test_chronological_ml_training_and_walk_forward(self) -> None:
        rng = np.random.default_rng(42)
        X = rng.normal(0.0, 1.0, size=(60, 16))
        y = 0.5 * X[:, 1] + 0.8 * X[:, 8] - 0.6 * X[:, 15] + rng.normal(0.0, 0.2, size=60)

        engine = PredictionEngine()
        split_res = ModelTrainer.train_and_evaluate(engine, X, y)
        self.assertEqual(split_res.train_size, 36)
        self.assertEqual(split_res.val_size, 12)
        self.assertEqual(split_res.test_size, 12)

        wf_rep = WalkForwardValidator.run_walk_forward(X, y, n_splits=3)
        self.assertEqual(wf_rep.n_folds, 3)
        self.assertGreater(wf_rep.mean_oos_directional_accuracy, 0.50)


if __name__ == "__main__":
    unittest.main()
