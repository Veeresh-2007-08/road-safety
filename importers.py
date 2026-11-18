"""
Data import and validation module for Bengaluru SafeRoute.
Processes CSV and GeoJSON inputs, verifies provenance, and prevents uncorroborated news
sources from being recorded as verified blackspots.
"""

import base64
import io
import json
import logging
from typing import Dict, Any, List, Tuple
import pandas as pd
from sqlalchemy.orm import Session

from src.models import (
    SourceModel,
    AccidentModel,
    BlackspotModel,
    SpeedLimitModel,
    RoadCurveModel,
    SourceSchema,
    AccidentSchema,
    BlackspotSchema,
    SpeedLimitSchema,
    RoadCurveSchema
)

logger = logging.getLogger(__name__)


def import_sources_from_records(records: List[Dict[str, Any]], db: Session) -> Dict[str, Any]:
    """Validate and insert or update data source provenance records."""
    success_count = 0
    errors = []

    for idx, rec in enumerate(records):
        try:
            validated = SourceSchema(**rec)
            existing = db.query(SourceModel).filter_by(source_id=validated.source_id).first()
            if existing:
                for k, v in validated.model_dump().items():
                    setattr(existing, k, v)
            else:
                db_obj = SourceModel(**validated.model_dump())
                db.add(db_obj)
            success_count += 1
        except Exception as e:
            errors.append(f"Row {idx+1} [Source ID {rec.get('source_id', '?')}]: {str(e)}")

    db.commit()
    return {"imported": success_count, "errors": errors}


def import_accidents_from_df(df: pd.DataFrame, db: Session) -> Dict[str, Any]:
    """Validate and insert accident crash records from pandas DataFrame."""
    success_count = 0
    errors = []

    for idx, row in df.iterrows():
        try:
            data = row.to_dict()
            # Clean NaN values
            clean_data = {k: (v if pd.notna(v) else None) for k, v in data.items()}
            validated = AccidentSchema(**clean_data)

            # Check that referenced source exists
            src = db.query(SourceModel).filter_by(source_id=validated.source_id).first()
            if not src:
                errors.append(f"Row {idx+1}: Foreign key source_id '{validated.source_id}' not found in sources registry.")
                continue

            existing = db.query(AccidentModel).filter_by(accident_id=validated.accident_id).first()
            if existing:
                for k, v in validated.model_dump().items():
                    setattr(existing, k, v)
            else:
                db_obj = AccidentModel(**validated.model_dump())
                db.add(db_obj)
            success_count += 1
        except Exception as e:
            errors.append(f"Row {idx+1} [ID {row.get('accident_id', '?')}]: {str(e)}")

    db.commit()
    return {"imported": success_count, "errors": errors}


def import_blackspots_from_geojson(geojson_dict: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Validate and insert blackspot records from GeoJSON.
    Enforces the strict rule: news-only sources cannot be imported as verified blackspots.
    """
    success_count = 0
    errors = []

    features = geojson_dict.get("features", [])
    for idx, feat in enumerate(features):
        try:
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [None, None])
            if "longitude" not in props and coords[0] is not None:
                props["longitude"] = coords[0]
            if "latitude" not in props and coords[1] is not None:
                props["latitude"] = coords[1]

            validated = BlackspotSchema(**props)

            # Check source verification rule
            src = db.query(SourceModel).filter_by(source_id=validated.source_id).first()
            if not src:
                errors.append(f"Feature {idx+1}: Source '{validated.source_id}' does not exist in registry.")
                continue

            # Critical rule: News articles cannot be saved as verified blackspots unless corroborated
            if src.source_type == "media_report" or "news" in src.source_name.lower():
                if validated.status in ("verified_official", "verified_admin"):
                    errors.append(
                        f"Feature {idx+1} [Blackspot {validated.blackspot_id}]: REJECTED. "
                        f"Media/News source '{src.source_name}' cannot designate verified blackspots."
                    )
                    continue

            existing = db.query(BlackspotModel).filter_by(blackspot_id=validated.blackspot_id).first()
            if existing:
                for k, v in validated.model_dump().items():
                    setattr(existing, k, v)
            else:
                db_obj = BlackspotModel(**validated.model_dump())
                db.add(db_obj)
            success_count += 1
        except Exception as e:
            errors.append(f"Feature {idx+1}: {str(e)}")

    db.commit()
    return {"imported": success_count, "errors": errors}


def import_speed_limits_from_df(df: pd.DataFrame, db: Session) -> Dict[str, Any]:
    """Validate and insert speed-limit records."""
    success_count = 0
    errors = []

    for idx, row in df.iterrows():
        try:
            data = row.to_dict()
            clean_data = {k: (v if pd.notna(v) else None) for k, v in data.items()}
            validated = SpeedLimitSchema(**clean_data)

            src = db.query(SourceModel).filter_by(source_id=validated.source_id).first()
            if not src:
                errors.append(f"Row {idx+1}: Source '{validated.source_id}' not found.")
                continue

            existing = db.query(SpeedLimitModel).filter_by(speed_limit_id=validated.speed_limit_id).first()
            if existing:
                for k, v in validated.model_dump().items():
                    setattr(existing, k, v)
            else:
                db_obj = SpeedLimitModel(**validated.model_dump())
                db.add(db_obj)
            success_count += 1
        except Exception as e:
            errors.append(f"Row {idx+1}: {str(e)}")

    db.commit()
    return {"imported": success_count, "errors": errors}


def import_curves_from_geojson(geojson_dict: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """Validate and insert road curve records from GeoJSON."""
    success_count = 0
    errors = []

    features = geojson_dict.get("features", [])
    for idx, feat in enumerate(features):
        try:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            curve_id = props.get("curve_id", f"CRV_UP_{idx+1}")
            road_name = props.get("road_name", "Unknown Bengaluru Corridor")
            curve_severity = props.get("curve_severity", "moderate")
            warning_text = props.get("warning_text", "Road curve detected.")
            source_id = props.get("source_id", "SRC_LOCAL_ADMIN")
            confidence_level = props.get("confidence_level", "geometry-derived")
            est_radius = props.get("estimated_radius_meters")

            curve_schema = RoadCurveSchema(
                curve_id=curve_id,
                road_name=road_name,
                geometry=json.dumps(geom),
                curve_severity=curve_severity,
                estimated_radius_meters=float(est_radius) if est_radius else None,
                warning_text=warning_text,
                source_id=source_id,
                confidence_level=confidence_level
            )

            existing = db.query(RoadCurveModel).filter_by(curve_id=curve_schema.curve_id).first()
            if existing:
                for k, v in curve_schema.model_dump().items():
                    setattr(existing, k, v)
            else:
                db_obj = RoadCurveModel(**curve_schema.model_dump())
                db.add(db_obj)
            success_count += 1
        except Exception as e:
            errors.append(f"Feature {idx+1}: {str(e)}")

    db.commit()
    return {"imported": success_count, "errors": errors}


def parse_dash_upload(
    contents: str,
    filename: str,
    target_type: str,
    db: Session
) -> Dict[str, Any]:
    """
    Decodes base64 string from Dash dcc.Upload and dispatches to appropriate importer.
    target_type: 'accidents', 'blackspots', 'speed_limits', 'curves', 'sources'
    """
    if not contents:
        return {"imported": 0, "errors": ["No upload content provided."]}

    try:
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
    except Exception as e:
        return {"imported": 0, "errors": [f"Failed to decode upload file: {str(e)}"]}

    filename_lower = filename.lower()

    if target_type == "accidents":
        if not filename_lower.endswith(".csv"):
            return {"imported": 0, "errors": ["Accident data must be uploaded as CSV."]}
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
        return import_accidents_from_df(df, db)

    elif target_type == "speed_limits":
        if not filename_lower.endswith(".csv"):
            return {"imported": 0, "errors": ["Speed limit data must be uploaded as CSV."]}
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
        return import_speed_limits_from_df(df, db)

    elif target_type == "blackspots":
        if not (filename_lower.endswith(".geojson") or filename_lower.endswith(".json")):
            return {"imported": 0, "errors": ["Blackspot data must be uploaded as GeoJSON."]}
        geojson_dict = json.loads(decoded.decode("utf-8"))
        return import_blackspots_from_geojson(geojson_dict, db)

    elif target_type == "curves":
        if not (filename_lower.endswith(".geojson") or filename_lower.endswith(".json")):
            return {"imported": 0, "errors": ["Curve data must be uploaded as GeoJSON."]}
        geojson_dict = json.loads(decoded.decode("utf-8"))
        return import_curves_from_geojson(geojson_dict, db)

    elif target_type == "sources":
        if filename_lower.endswith(".csv"):
            df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
            records = df.to_dict(orient="records")
        else:
            records = json.loads(decoded.decode("utf-8"))
        return import_sources_from_records(records, db)

    return {"imported": 0, "errors": [f"Unrecognized target type: {target_type}"]}
