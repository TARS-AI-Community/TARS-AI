"""
module_engineTrainer.py

Text Classification Training Module for GPTARS Application.

This module uses labeled training data to build a Naive Bayes-based text classifier with TF-IDF vectorization. 
The trained model and vectorizer are saved as pickle files for use by other components of the application.
"""

# === Standard Libraries ===
import os
from datetime import datetime
import pandas as pd
import joblib
from sklearn.naive_bayes import MultinomialNB
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

# === Constants ===
DEFAULT_TRAINING_DATA_PATH = 'engine/training/training_data.csv'
DEFAULT_MODEL_PATH = 'engine/pickles/naive_bayes_model.pkl'
DEFAULT_VECTORIZER_PATH = 'engine/pickles/tfidf_vectorizer.pkl'

def delete_existing_files(nb_classifier_path=DEFAULT_MODEL_PATH, vectorizer_path=DEFAULT_VECTORIZER_PATH):
    """
    Delete existing model and vectorizer files if they exist.
    """
    for file_path in [nb_classifier_path, vectorizer_path]:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: {file_path} deleted successfully.")

def sort_and_save_data(df):
    """
    Sort the training data by labels and save it as a new CSV file.

    Parameters:
    - df (DataFrame): Training data DataFrame.
    """
    sorted_df = df.sort_values(by='label')
    sorted_df.to_csv('engine/training/sorted_training_data.csv', index=False)
    # print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Data sorted and saved as 'sorted_training_data.csv'.")

def train_and_validate_model(df_train, nb_classifier_path, vectorizer_path):
    """
    Train a Naive Bayes classifier with TF-IDF vectorization and validate the model.

    Parameters:
    - df_train (DataFrame): Raw training data.
    - nb_classifier_path (str): Path to save the trained classifier.
    - vectorizer_path (str): Path to save the vectorizer.
    """
    # Split data into training and validation sets
    train_df, val_df = train_test_split(df_train, test_size=0.20, stratify=df_train['label'], random_state=42)

    # Remove duplicates and handle data leakage
    train_df, val_df = clean_data(train_df, val_df)

    # Mix up (shuffle) the data to avoid sequential biases
    for _ in range(3):
        train_df = train_df.sample(frac=1).reset_index(drop=True)
        val_df = val_df.sample(frac=1).reset_index(drop=True)

    # Train the model
    vectorizer = TfidfVectorizer()
    train_vectors = vectorizer.fit_transform(train_df['query'])
    val_vectors = vectorizer.transform(val_df['query'])

    nb_classifier = MultinomialNB(alpha=0.1)
    nb_classifier.fit(train_vectors, train_df['label'])

    # Calibrate the classifier
    calibrated_classifier = CalibratedClassifierCV(nb_classifier, method='sigmoid')
    calibrated_classifier.fit(train_vectors, train_df['label'])

    # Validate the model
    val_predictions = calibrated_classifier.predict(val_vectors)
    accuracy = accuracy_score(val_df['label'], val_predictions)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Validation Accuracy: {accuracy:.2%}")

    # Save the model and vectorizer
    joblib.dump(nb_classifier, nb_classifier_path)
    joblib.dump(vectorizer, vectorizer_path)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Model and vectorizer saved successfully.")

    return accuracy

def clean_data(train_df, val_df):
    """
    Clean training and validation data by removing duplicates and checking for data leakage.

    Parameters:
    - train_df (DataFrame): Training data.
    - val_df (DataFrame): Validation data.

    Returns:
    - tuple: Cleaned training and validation DataFrames.
    """
    # Remove duplicates
    train_df = train_df.drop_duplicates(subset=['query'])
    val_df = val_df.drop_duplicates(subset=['query'])

    # Check for data leakage
    common_queries = set(train_df['query']).intersection(set(val_df['query']))
    if common_queries:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Training data leaked into validation data!")
        val_df = val_df[~val_df['query'].isin(common_queries)]
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Validation data cleaned.")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: No data leakage detected.")

    return train_df, val_df

# === Main Function ===
def train_text_classifier(
    training_data_path=DEFAULT_TRAINING_DATA_PATH,
    nb_classifier_path=DEFAULT_MODEL_PATH,
    vectorizer_path=DEFAULT_VECTORIZER_PATH,
    user_input='y'
):
    """
    Train a text classification model using labeled training data.

    Parameters:
    - training_data_path (str): Path to the training data CSV file.
    - nb_classifier_path (str): Path to save the trained Naive Bayes classifier.
    - vectorizer_path (str): Path to save the TF-IDF vectorizer.
    - user_input (str): User input to control data preparation ('y' for training, 's' for sorting).
    """
    # print(f"Using scikit-learn version: {sklearn_version}")

    # Remove existing model and vectorizer files
    delete_existing_files(nb_classifier_path, vectorizer_path)

    # Load the training data
    df_train = pd.read_csv(training_data_path)

    # Data preparation based on user input
    if user_input.lower() == 's':
        sort_and_save_data(df_train)
    elif user_input.lower() == 'y':
        train_and_validate_model(df_train, nb_classifier_path, vectorizer_path)
    else:
        print("Script terminated. Run the script again and type 'y' or 's' when prompted.")

# === Script Execution ===
if __name__ == '__main__':
    train_text_classifier()