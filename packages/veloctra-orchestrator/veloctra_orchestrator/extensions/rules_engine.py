import pyarrow as pa
import pyarrow.compute as pc
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class RulesEngine:
    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = rules

    def apply_rules(self, batch: pa.RecordBatch) -> pa.RecordBatch:
        if not self.rules:
            return batch
            
        mask = None
        for rule in self.rules:
            field = rule.get("field")
            op = rule.get("operator")
            val = rule.get("value")
            
            if not field or not op:
                continue
                
            try:
                # Basic pyarrow compute filtering
                col_data = batch[field]
                if op == "==":
                    cond = pc.equal(col_data, val)
                elif op == "!=":
                    cond = pc.not_equal(col_data, val)
                elif op == ">":
                    cond = pc.greater(col_data, val)
                elif op == ">=":
                    cond = pc.greater_equal(col_data, val)
                elif op == "<":
                    cond = pc.less(col_data, val)
                elif op == "<=":
                    cond = pc.less_equal(col_data, val)
                elif op == "in":
                    cond = pc.is_in(col_data, value_set=pa.array(val))
                elif op == "not_in":
                    cond = pc.invert(pc.is_in(col_data, value_set=pa.array(val)))
                else:
                    logger.warning(f"[RulesEngine] Unsupported operator {op}")
                    continue
                    
                if mask is None:
                    mask = cond
                else:
                    mask = pc.and_(mask, cond)
            except Exception as e:
                logger.error(f"[RulesEngine] Error applying rule {rule}: {e}")
                
        if mask is not None:
            return batch.filter(mask)
        return batch
