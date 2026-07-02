import logging
import topic_scorer
import script_scorer
import visual_scorer
import upload_optimizer
import analytics_sync

logger = logging.getLogger("YoutubeAutomator")

class LearningEngine:
    @staticmethod
    def score_and_rank_topics(candidate_topics: list[str]) -> list[tuple[str, float]]:
        """
        Returns topics sorted by predicted performance score.
        """
        try:
            kw_weights = topic_scorer.get_keyword_weight_map()
            scored = []
            for topic in candidate_topics:
                score = topic_scorer.score_topic(topic, kw_weights)
                scored.append((topic, score))
            # Sort by score descending
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored
        except Exception as e:
            logger.error(f"[Learning Engine] Error scoring topics: {e}")
            return [(topic, 50.0) for topic in candidate_topics]

    @staticmethod
    def build_script_context_block() -> str:
        """
        Returns a string to prepend to every LLM script generation prompt.
        """
        try:
            return script_scorer.build_script_context_block()
        except Exception as e:
            logger.error(f"[Learning Engine] Error building script context block: {e}")
            return ""

    @staticmethod
    def suggest_visual_sequence(algorithm_category: str) -> list[str]:
        """
        Returns the best beat visual_type sequence for the given algorithm category.
        """
        try:
            return visual_scorer.suggest_visual_sequence(algorithm_category)
        except Exception as e:
            logger.error(f"[Learning Engine] Error suggesting visual sequence: {e}")
            return None

    @staticmethod
    def get_best_upload_slot() -> tuple[int, int]:
        """
        Returns (hour, day_of_week) for the next optimal upload.
        """
        try:
            return upload_optimizer.get_best_upload_slot()
        except Exception as e:
            logger.error(f"[Learning Engine] Error getting best upload slot: {e}")
            import random
            return (12, random.randint(0, 6)) # safe default

    @staticmethod
    def get_title_template() -> str:
        """
        Returns a title format string based on highest-CTR historical patterns.
        """
        try:
            return upload_optimizer.get_title_template()
        except Exception as e:
            logger.error(f"[Learning Engine] Error getting title template: {e}")
            return "Master [Topic] | [Catchy Hinglish] #Shorts"

    @staticmethod
    def run_learning_cycle():
        """
        Recomputes all modular preference tables.
        Called after analytics_sync completes.
        """
        logger.info("[Learning Engine] Re-computing all intelligence tables...")
        try:
            topic_scorer.update_keyword_weights()
            script_scorer.update_script_preferences()
            visual_scorer.update_visual_preferences()
            upload_optimizer.update_upload_preferences()
            logger.info("[Learning Engine] Learning cycle complete.")
        except Exception as e:
            logger.error(f"[Learning Engine] Learning cycle failed: {e}")
