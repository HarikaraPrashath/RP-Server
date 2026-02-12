import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer

from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, confusion_matrix, classification_report

from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout
from tensorflow.keras.callbacks import EarlyStopping
from tensorflow.keras.regularizers import l2
from tensorflow.keras.utils import to_categorical

# ================================
# 1) Load Dataset
# ================================
df = pd.read_csv(r"C:\Users\user\Desktop\New folder\Reserch\New folder\RP-Server\CV_extractor\data\cv_job_dataset.csv")

# ================================
# 2) Convert Fit_Score -> Classes (Low/Medium/High)
#    You can adjust thresholds if you want
# ================================
# Example thresholds:
#   Low:    < 40
#   Medium: 40 - 70
#   High:   > 70
bins = [-1, 40, 70, 101]
labels = [0, 1, 2]  # 0=Low, 1=Medium, 2=High

df["Fit_Class"] = pd.cut(df["Fit_Score"], bins=bins, labels=labels).astype(int)

# ================================
# 3) Features and Target
# ================================
X = df.drop(["Fit_Score", "Fit_Class"], axis=1)
y = df["Fit_Class"]

# ================================
# 4) Column Types
# ================================
numerical_cols = ["Age", "Experience_Years"]

categorical_cols = [
    "Gender", "Education", "Skills",
    "Previous_Companies", "Certifications",
    "Job_Role", "Job_Description"
]

# ================================
# 5) Preprocessing (OneHot + Scaling)
# ================================
preprocessor = ColumnTransformer(
    transformers=[
        ("num", StandardScaler(), numerical_cols),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical_cols)
    ]
)

X_processed = preprocessor.fit_transform(X)

# ================================
# 6) Train-Test Split
# ================================
X_train, X_test, y_train, y_test = train_test_split(
    X_processed, y,
    test_size=0.2,
    random_state=42,
    stratify=y  # keeps class ratio similar in train/test
)

# ================================
# 7) One-hot encode target for ANN
# ================================
num_classes = len(np.unique(y))
y_train_cat = to_categorical(y_train, num_classes=num_classes)
y_test_cat = to_categorical(y_test, num_classes=num_classes)

# ================================
# 8) Build Simple ANN Classifier
# ================================
model = Sequential([
    Dense(128, activation="relu", kernel_regularizer=l2(1e-4), input_shape=(X_train.shape[1],)),
    Dropout(0.3),
    Dense(64, activation="relu", kernel_regularizer=l2(1e-4)),
    Dropout(0.3),
    Dense(num_classes, activation="softmax")  # classification output
])

model.compile(
    optimizer="adam",
    loss="categorical_crossentropy",
    metrics=["accuracy"]
)

# ================================
# 9) Train
# ================================
early_stop = EarlyStopping(
    monitor="val_loss",
    patience=5,
    restore_best_weights=True
)

model.fit(
    X_train, y_train_cat,
    validation_split=0.1,
    epochs=25,
    batch_size=16,
    verbose=1,
    callbacks=[early_stop]
)

# ================================
# 10) Predict + Evaluation Metrics
# ================================
y_pred_probs = model.predict(X_test)
y_pred = np.argmax(y_pred_probs, axis=1)

acc = accuracy_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred, average="weighted")
prec = precision_score(y_test, y_pred, average="weighted")
rec = recall_score(y_test, y_pred, average="weighted")

print("\n==== Evaluation Metrics ====")
print("Accuracy :", acc)
print("F1-score :", f1)
print("Precision:", prec)
print("Recall   :", rec)

print("\n==== Confusion Matrix ====")
print(confusion_matrix(y_test, y_pred))

print("\n==== Classification Report ====")
print(classification_report(y_test, y_pred, target_names=["Low", "Medium", "High"]))
