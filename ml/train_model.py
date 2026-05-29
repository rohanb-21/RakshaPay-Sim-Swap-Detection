import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, roc_auc_score, f1_score, precision_score, recall_score
from xgboost import XGBClassifier

SEED = 42
np.random.seed(SEED)
OUT_DIR = os.path.dirname(__file__)


def generate_data(n_legit=6000, n_fraud=4000):
    records = []

    # Legitimate samples - include unknown device and external IP as normal
    for _ in range(n_legit):
        records.append({
            "hours_since_sim_swap": -1,          # No swap = legitimate
            "is_known_device": np.random.choice([1, 0], p=[0.5, 0.5]),
            "transaction_amount": 0,
            "is_external_ip": np.random.choice([1, 0], p=[0.7, 0.3]),
            "login_hour": np.random.randint(0, 23),
            "failed_attempts_1h": 0,
            "account_age_days": np.random.randint(30, 1000),
            "txns_last_24h": np.random.randint(0, 5),
            "label": 0
        })

    
    # Fraudulent samples - SIM swap is the KEY differentiator
    for _ in range(n_fraud):
        hours = np.random.choice([
            np.random.uniform(0, 1),    # Critical: 0-1hr
            np.random.uniform(1, 24),   # High: 1-24hr
            np.random.uniform(24, 72),  # Medium: 24-72hr
        ], p=[0.5, 0.3, 0.2])
        records.append({
            "hours_since_sim_swap": hours,
            "is_known_device": np.random.choice([1, 0], p=[0.2, 0.8]),
            "transaction_amount": 0,
            "is_external_ip": np.random.choice([1, 0], p=[0.7, 0.3]),
            "login_hour": np.random.randint(0, 23),
            "failed_attempts_1h": 0,
            "account_age_days": np.random.randint(1, 500),
            "txns_last_24h": np.random.randint(0, 5),
            "label": 1
        })

    df = pd.DataFrame(records).sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df


def train():
    print("🤖 RakshaPay — Training Fraud Detection Model")
    print("=" * 50)

    df = generate_data()
    print(f"Dataset: {len(df)} records | Fraud: {df.label.sum()} | Legit: {(df.label==0).sum()}")

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

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    spw = len(y_train[y_train==0]) / max(len(y_train[y_train==1]), 1)

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=spw,
        eval_metric="logloss",
        random_state=SEED,
        verbosity=0,
    )
    model.fit(X_train_s, y_train)

    y_pred = model.predict(X_test_s)
    y_prob = model.predict_proba(X_test_s)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    print(f"\n📊 Model Performance:")
    print(f"   AUC-ROC   : {auc:.4f}")
    print(f"   Precision : {precision:.4f}")
    print(f"   Recall    : {recall:.4f}")
    print(f"   F1 Score  : {f1:.4f}")
    print()
    print(classification_report(y_test, y_pred, target_names=["Legit", "Fraud"]))

    # Test prediction for fraud scenario
    fraud_test = np.array([[0.5, 0, 50000, 1, 3, 2, 90, 5]])
    fraud_test_s = scaler.transform(fraud_test)
    fraud_prob = model.predict_proba(fraud_test_s)[0][1]
    print(f"✅ Fraud scenario test probability: {fraud_prob*100:.1f}% (should be HIGH)")

    # Test prediction for safe scenario
    safe_test = np.array([[-1, 1, 1000, 0, 13, 0, 365, 2]])
    safe_test_s = scaler.transform(safe_test)
    safe_prob = model.predict_proba(safe_test_s)[0][1]
    print(f"✅ Safe scenario test probability: {safe_prob*100:.1f}% (should be LOW)")

    model_path = os.path.join(OUT_DIR, "fraud_model.pkl")
    scaler_path = os.path.join(OUT_DIR, "scaler.pkl")
    meta_path = os.path.join(OUT_DIR, "model_meta.json")

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)

    meta = {
        "features": features,
        "auc": round(auc, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "trained_on": f"{len(df)} samples",
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\n✅ Model saved → {model_path}")
    print(f"✅ Scaler saved → {scaler_path}")
    print(f"✅ Meta saved → {meta_path}")


if __name__ == "__main__":
    train()