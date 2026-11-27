"""Pure IA cost arithmetic in historical micro-USD units; no tariff or budget policy."""
import json
import math


def reservation(body,pi,po,tokens,*,dumps=json.dumps,ceil=math.ceil):
    # Conservative UTF-8 byte bound, not a guaranteed provider token ceiling.
    bound=len(dumps(body,ensure_ascii=False).encode())+1024
    return ceil(bound*pi+tokens*po)


def measured(input_tokens,output_tokens,pi,po,*,ceil=math.ceil):
    return ceil(input_tokens*pi+output_tokens*po)
