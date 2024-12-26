import pandas as pd
import joblib
from sklearn import __version__ as sklearn_version
from sklearn.naive_bayes import MultinomialNB
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
import os
from datetime import datetime

def train_text_classifier(training_data_path='module_engine/training/training_data.csv',
                          nb_classifier_path='module_engine/pickles/naive_bayes_model.pkl',
                          vectorizer_path='module_engine/pickles/tfidf_vectorizer.pkl',
                          user_input='y'):
    #print(f"Using scikit-learn version: {sklearn_version}")

    # Check and delete existing pickle files
    for file_path in [nb_classifier_path, vectorizer_path]:
        if os.path.exists(file_path):
            os.remove(file_path)
            #print(f"{file_path} file deleted successfully.")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: {file_path} file deleted successfully.")

    df_train = pd.read_csv(training_data_path)

    if user_input.lower() == 's':
        #print("Sorting...")
        df_train_sorted = df_train.sort_values(by='label')
        df_train_sorted.to_csv('module_engine/training/sorted_training_data.csv', index=False)
        #print("Data sorted by label and saved to 'sorted_training_data.csv'")
    elif user_input.lower() == 'y':
        #print("Loading and preparing the Raw Training data")

        train_df = pd.read_csv("module_engine/training/training_data.csv")

        #print("Splitting data into training and validation sets")
        train_df, val_df = train_test_split(train_df, test_size=0.20, stratify=train_df['label'], random_state=42)

        #print("Removing duplicates from validation data")
        merged_df = train_df.merge(val_df, indicator=True, how='outer')
        duplicates = merged_df[merged_df['_merge'] == 'both']
        if not duplicates.empty:
            #print("Duplicates found:")
            for index, row in duplicates.iterrows():
                print(row)
        else:
            #print("No duplicates found.")
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: No duplicates found.")
        df_train = merged_df[merged_df['_merge'] == 'left_only'].drop(columns=['_merge'])

        
        #print("Mix up the data")
        i = 0
        while i < 3:
            df_train = df_train.sample(frac=1).reset_index(drop=True)
            val_df = val_df.sample(frac=1).reset_index(drop=True)
            i = i + 1

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Split data into queries and labels and remove duplicates")
        train_df = train_df.drop_duplicates(subset=['query'])
        val_df = val_df.drop_duplicates(subset=['query'])


        #print("Checking for data leakage")
        common_queries = set(train_df['query']).intersection(set(val_df['query']))
        if common_queries:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Training data leaked into validation data!")
            val_df = val_df[~val_df['query'].isin(common_queries)]
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Validation data has been cleaned.")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: No training data leaked into validation data.")


        #df_train.to_csv('module_engine/training/training_data_used.csv', index=False)
        #val_df.to_csv('module_engine/training/validation_data_used.csv', index=False)

        # Vectorization and Model Training
        vectorizer = TfidfVectorizer()
        train_vectors = vectorizer.fit_transform(train_df['query'])
        val_vectors = vectorizer.transform(val_df['query'])

        nb_classifier = MultinomialNB(alpha=0.1)
        nb_classifier.fit(train_vectors, train_df['label'])

        calibrated_classifier = CalibratedClassifierCV(nb_classifier, method='sigmoid')
        calibrated_classifier.fit(train_vectors, train_df['label'])

        val_predictions = calibrated_classifier.predict(val_vectors)
        accuracy = accuracy_score(val_df['label'], val_predictions)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] LOAD: Validation Accuracy: {accuracy:.2%}")
        # Save the model and vectorizer
        joblib.dump(nb_classifier, 'module_engine/pickles/naive_bayes_model.pkl')
        joblib.dump(vectorizer, 'module_engine/pickles/tfidf_vectorizer.pkl')

        #print('Done! Trained models saved.')
        
        # Placeholder to return accuracy, for instance:
        return 0.95  # This should be replaced with the actual accuracy variable
    else:
        print("Script terminated. If you want to continue, run the script again and type 'Y' when prompted.")

