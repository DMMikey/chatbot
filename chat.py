import random
import json
import torch
from model import NeuralNet  # Use your NeuralNet class defined in model.py
from nltk_utils import tokenize, bag_of_words  # Use your functions from nltk_utils.py
from utils import text_to_speech
from nwp_train_pytorch import nwp


class Chatbot:
    def __init__(self, model, all_words, tags, intents):
        self.model = model
        self.all_words = all_words
        self.tags = tags
        self.intents = intents
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)
        self.name = "Jarvis"

    def predict_class(self, sentence):
        sentence = tokenize(sentence)
        X = bag_of_words(sentence, self.all_words)
        X = X.reshape(1, X.shape[0])
        X = torch.from_numpy(X).to(self.device)

        output = self.model(X)
        _, predicted = torch.max(output, dim=1)
        tag = self.tags[predicted.item()]
        probs = torch.softmax(output, dim=1)
        prob = probs[0][predicted.item()]

        return tag, prob

    def get_response(self, tag):
        for intent in self.intents["intents"]:
            if tag == "goodbye":
                text_to_speech(
                    bot_name=self.name, text=nwp("I am waiting for your orders sir!", 5)
                )
                return (
                    "exit"  # Add a return statement to exit the loop in the main code
                )
            if tag == intent["tag"]:
                response = random.choice(intent["responses"])
                if response:
                    return text_to_speech(bot_name=self.name, text=nwp(response, 20))
                else:
                    return text_to_speech(
                        bot_name=self.name,
                        text="I'm sorry, I don't have a response for that.",
                    )
        return text_to_speech(
            bot_name=self.name, text="I don't understand, can you ask something else?"
        )

    def generate_text(self, prompt, max_length=50):
        """
        Basit bir metin üretimi yapar. Bu metot, verilen bir başlangıç metnine dayanarak yeni metin üretir.
        """
        # Prompt'u tokenize et ve bag of words'e dönüştür
        prompt_tokens = tokenize(prompt)
        prompt_bow = (
            bag_of_words(prompt_tokens, self.all_words).reshape(1, -1).to(self.device)
        )

        # Metin üretme modelini kullanarak metin üret
        generated_words = []
        for _ in range(max_length):
            with torch.no_grad():
                output = self.text_gen_model(prompt_bow)
            _, predicted = torch.max(output, dim=1)
            predicted_word = self.all_words[predicted.item()]
            generated_words.append(predicted_word)

            # Yeni kelimeyi prompt'a ekle ve tekrar bag of words'e dönüştür
            prompt += " " + predicted_word
            prompt_tokens = tokenize(prompt)
            prompt_bow = (
                bag_of_words(prompt_tokens, self.all_words)
                .reshape(1, -1)
                .to(self.device)
            )

        return " ".join(generated_words)

    def chat(self, user_input):
        tag, prob = self.predict_class(user_input)
        if prob > 0.75:
            return self.get_response(tag)
        else:
            return text_to_speech(bot_name=self.name, text="I didn't understand.")


if __name__ == "__main__":
    data = torch.load("data.pth")
    input_size = data["input_size"]
    hidden_size = data["hidden_size"]
    output_size = data["output_size"]
    all_words = data["all_words"]
    tags = data["tags"]
    model_state = data["model_state"]

    model = NeuralNet(input_size, hidden_size, output_size).to(
        torch.device("cuda" if torch.cuda.is_available() else "cpu")
    )
    model.load_state_dict(model_state)
    model.eval()

    intents = json.load(open("intents.json", "r"))
    chatbot = Chatbot(model, all_words, tags, intents)

    while True:
        message = input("You: ")
        response = chatbot.chat(message)
        if (response) == "exit":
            break
