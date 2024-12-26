import requests
import joblib 
from module_websearch import *
from module_vision import *
from datetime import datetime

#module_engine
model_filename = 'module_engine/pickles/naive_bayes_model.pkl'
vectorizer_filename = 'module_engine/pickles/tfidf_vectorizer.pkl'
nb_classifier = joblib.load(model_filename)
tfidf_vectorizer = joblib.load(vectorizer_filename)

#MODULE FUNCTIONS
def predict_category(user_input):
    # Transform the user input using the pre-trained TF-IDF vectorizer
    user_input_vectorized = tfidf_vectorizer.transform([user_input])

    # Use the pre-trained Naive Bayes classifier to predict the category
    predicted_category = nb_classifier.predict(user_input_vectorized)[0]

    return predicted_category

def predict_module(user_input):
    query_vector = tfidf_vectorizer.transform([user_input])
    predictions = nb_classifier.predict(query_vector)
    predicted_probabilities = nb_classifier.predict_proba(query_vector)

    # Get the predicted class and its corresponding probability
    predicted_class = predictions[0]
    max_probability = max(predicted_probabilities[0])
    #print(max_probability)
    #print(predicted_class)

    percentage = max_probability * 100
    formatted_percentage = f"{percentage:.1f}"  # Format to one decimal place
    #print(f"Module: {predicted_class} @ {formatted_percentage}%")

    if max_probability < 0.75:
        percentageleft = 100 - percentage
        formatted_percentageleft = f"{percentageleft:.0f}"  # Format to no decimal places

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TOOL: {predicted_class} @ {formatted_percentage}%")
        return None, max_probability
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TOOL: {predicted_class} @ {formatted_percentage}%")
        return predicted_class, max_probability

def check_for_module(user_input):
    global module_engine
    predicted_class, probability = predict_module(user_input)

    if "search google" in user_input:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] TOOL: Forced Search")
        predicted_class = "Search"

    #Guesses
    if predicted_class is not None:
        print(f"Predicted Class: {predicted_class}")
        print(f"Probability: {probability}")

        if predicted_class == "Weather":
            print(f"Weather MODULE")
            weather_info = search_google(user_input)
            module_engine = f"*Using tool Web Search* use the following results from a realtime websearch for your response: {weather_info}"

        if predicted_class == "News":
            print(f"News MODULE")
            result = get_google_news(user_input)
            module_engine = f"*Using tool Web Search* Summarize the news from the following websearch results: {result}"

        if predicted_class == "Vision":
            print(f"Vision MODULE")
            result = describe_camera_view()
            module_engine = f"*Using tool Vision* The following is a summary of what TARS can see: {result}"
            print(result)

        if predicted_class == "Search":
            print(f"Search MODULE")
            result = search_google(user_input)
            module_engine = f"*Using tool Web Search* Use this answer from google to respond to the user: {result}"
            print(module_engine)
            
        if predicted_class == "goodbye":
            print(f"Goodbye Module")
            module_engine = f"*User is leaving the chat politely*"

    else:
        module_engine = "No_Tool"
        #print(f"No Module needed. Maximum probability: {probability}")
    
    return module_engine