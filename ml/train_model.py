"""
VaultX Fraud Detection — ML Model Training
==========================================
Generates realistic synthetic fraud data and trains an XGBoost classifier.
Run once:  python3 ml/train_model.py
Outputs:   ml/fraud_model.pkl  +  ml/model_meta.json
"""
import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, roc_auc_score,
    precision_score, recall_score, f1_score
)
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)

OUT_DIR = os.path.dirname(__file__)


def generate_data(n_legit=8000, n_fraud=2000):
    """
    Generates synthetic login/transaction records.
    Features reflect real-world fraud signals.
    """
    records = []

    # ── Legitimate samples ────────────────────────────────────
    for _ in range(n_legit):
        records.append({
            "hours_since_sim_swap": -1,          # -1 = no swap
            "is_known_device":      np.random.choice([1, 0], p=[0.92, 0.08]),
            "transaction_amount":   np.random.exponential(scale=3000),
            "is_external_ip":       np.random.choice([1, 0], p=[0.1, 0.9]),
            "login_hour":           int(np.clip(np.random.normal(13, 4), 0, 23)),
            "failed_attempts_1h":   np.random.choice([0, 1, 2], p=[0.85, 0.12, 0.03]),
            "account_age_days":     int(np.random.uniform(30, 1500)),
            "txns_last_24h":        int(np.clip(np.random.exponential(1.5), 0, 20)),
            "label": 0
        })

    # ── Fraudulent samples ────────────────────────────────────
    for _ in range(n_fraud):
        swap_hours = np.random.uniform(0.1, 72)   # very recent swap
        records.append({
            "hours_since_sim_swap": swap_hours,
            "is_known_device":      np.random.choice([1, 0], p=[0.05, 0.95]),
            "transaction_amount":   np.random.uniform(30000, 200000),
            "is_external_ip":       np.random.choice([1, 0], p=[0.75, 0.25]),
            "login_hour":           int(np.random.choice(
                                        list(range(0, 6)) + list(range(22, 24))
                                    )),             # odd hours
            "failed_attempts_1h":   np.random.choice([0, 1, 2, 3], p=[0.3, 0.3, 0.25, 0.15]),
            "account_age_days":     int(np.random.uniform(1, 200)),
            "txns_last_24h":        int(np.random.uniform(3, 25)),
            "label": 1
        })

    df = pd.DataFrame(records).sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df


def train():
    print("🤖 VaultX — Training Fraud Detection Model")
    print("=" * 50)

    df = generate_data()
    print(f"Dataset: {len(df)} records  |  Fraud: {df.label.sum()}  |  Legit: {(df.label==0).sum()}")

    features = [
        "hours_since_sim_swap", "is_known_device", "transaction_amount",
        "is_external_ip", "login_hour", "failed_attempts_1h",
        "account_age_days", "txns_last_24h"
    ]

    X = df[features]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )

    # Scale
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    # XGBoost
    spw = len(y_train[y_train==0]) / max(len(y_train[y_train==1]), 1)
    model = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=SEED,
        verbosity=0,
    )
    model.fit(X_train_s, y_train)

    # Evaluate
    y_pred      = model.predict(X_test_s)
    y_prob      = model.predict_proba(X_test_s)[:, 1]
    auc         = roc_auc_score(y_test, y_prob)
    precision   = precision_score(y_test, y_pred)
    recall      = recall_score(y_test, y_pred)
    f1          = f1_score(y_test, y_pred)
    cv_scores   = cross_val_score(model, scaler.transform(X), y, cv=5, scoring="roc_auc")

    print(f"\n📊 Model Performance:")
    print(f"   AUC-ROC     : {auc:.4f}")
    print(f"   Precision   : {precision:.4f}")
    print(f"   Recall      : {recall:.4f}")
    print(f"   F1 Score    : {f1:.4f}")
    print(f"   CV AUC (5x) : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
    print()
    print(classification_report(y_test, y_pred, target_names=["Legit", "Fraud"]))

    # Save
    model_path  = os.path.join(OUT_DIR, "fraud_model.pkl")
    scaler_path = os.path.join(OUT_DIR, "scaler.pkl")
    meta_path   = os.path.join(OUT_DIR, "model_meta.json")

    joblib.dump(model,  model_path)
    joblib.dump(scaler, scaler_path)

    meta = {
        "features":  features,
        "auc":       round(auc, 4),
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "cv_auc_mean": round(float(cv_scores.mean()), 4),
        "trained_on": f"{len(df)} samples",
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"✅ Model saved  → {model_path}")
    print(f"✅ Scaler saved → {scaler_path}")
    print(f"✅ Meta saved   → {meta_path}")
    return model, scaler, meta


if __name__ == "__main__":
    train()
