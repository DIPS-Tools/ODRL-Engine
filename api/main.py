from io import StringIO
import json
import os
import tempfile
import pandas as pd
from fastapi import FastAPI, HTTPException


import rdf_utils
import SotW_generator
import ODRL_Evaluator as Evaluator
import validate

from api.models import (
    EvaluateRequest,
    EvaluateResponse,
    PolicyFeaturesRequest,
    PolicyFeaturesResponse,
    ValidatePolicyRequest,
    ValidatePolicyResponse,
)

EXTERNAL_PREFIX = os.environ.get("ODRL_EXTERNAL_PREFIX", "").strip("/")
ROOT_PATH = f"/{EXTERNAL_PREFIX}/api" if EXTERNAL_PREFIX else "/api"

app = FastAPI(
    title="ODRL Evaluator API",
    version="1.0.0",
    root_path=ROOT_PATH,
)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/evaluate_policy_on_sotw",
    response_model=EvaluateResponse
)
def evaluate_policy_on_sotw(request: EvaluateRequest):

    result = Evaluator.evaluate_ODRL_from_strings(
        request.policy,
        request.sotw,
        request.evaluation_state
    )

    (
        evaluation_state,
        validity,
        permission_rows,
        prohibition_rows,
        obligations,
        duties,
        consequences,
        remedies
    ) = result

    return EvaluateResponse(
        evaluation_state=evaluation_state,
        valid=bool(validity),
        rows_violating_permissions=permission_rows,
        rows_violating_prohibitions=prohibition_rows,
        obligations_not_satisfied=obligations,
        unfulfilled_duties=duties,
        unfulfilled_consequences=consequences,
        unfulfilled_remedies=remedies
    )

@app.post(
    "/get_policy_features",
    response_model=PolicyFeaturesResponse
)
def get_policy_features(request: PolicyFeaturesRequest):
    try:
        features = SotW_generator.extract_features_list_from_string(
            request.policy
        )
        return PolicyFeaturesResponse(features=features)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/validate_odrl_policy",
    response_model=ValidatePolicyResponse,
)
def validate_odrl_policy(request: ValidatePolicyRequest):
    policy_text = (
        request.policy
        if isinstance(request.policy, str)
        else json.dumps(request.policy)
    )
    print(
        json.dumps({
            "event": "validate_odrl_policy.input",
            "policy": request.policy,
        }),
        flush=True,
    )

    policy_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".jsonld",
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as policy_file:
            policy_file.write(policy_text)
            policy_path = policy_file.name
        # calling diagnose_ODRL to validate the input odrl
        errors, warnings, parsed_info, is_valid = validate.diagnose_ODRL(
            policy_path
        )
        diagnostic_report = "\n".join([
            *errors,
            *warnings,
            *parsed_info,
        ])

        response = ValidatePolicyResponse(
            valid=bool(is_valid),
            diagnostic_report=diagnostic_report,
        )
        print(
            json.dumps({
                "event": "validate_odrl_policy.output",
                **response.model_dump(),
            }),
            flush=True,
        )
        return response
    except Exception as exc:
        detail = f"Unable to parse or validate ODRL policy: {exc}"
        print(
            json.dumps({
                "event": "validate_odrl_policy.output",
                "status_code": 400,
                "detail": detail,
            }),
            flush=True,
        )
        raise HTTPException(
            status_code=400,
            detail=detail,
        ) from exc
    finally:
        if policy_path and os.path.exists(policy_path):
            os.remove(policy_path)
