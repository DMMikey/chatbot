import torch
from models.GPTModel import GPTLanguageModel
from Test import decode, encode, hyperParams
import time

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

model = GPTLanguageModel(hyperParams)
model.load_state_dict(torch.load("checkpoints/1715423841.6194382/checkpoint:10.h5"))


def generate_text(
        context: str,
        max_new_tokens: int = 500,
):
    generated_text = ""
    context = torch.tensor(encode(context), device=device)[
              None, :
              ]
    generated_text += decode(
        model.generate(context, max_new_tokens)[0].tolist()
    )
    return generated_text


start_time = time.time()
print(generate_text(context="my name is", max_new_tokens=10))
end_time = time.time()
print(f"Time elapsedÏ: {end_time - start_time}")
