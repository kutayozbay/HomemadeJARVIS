#Secret API Key = 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


import openai

openai.api_key = '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'

messages = [ {"role": "system", "content": "You are a intelligent assistant."} ]

while True:
    message = input("User : ")
    if message:
        messages.append(
            {"role": "user", "content": message},
        )
        chat = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=messages
        )

    reply = chat.choices[0].message.content
    print(f"ChatGPT: {reply}")
    messages.append({"role": "assistant", "content": reply})
