from os import environ
import traceback
import logging
import requests
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

rollup_server = environ["ROLLUP_HTTP_SERVER_URL"]
logger.info(f"HTTP rollup_server url is {rollup_server}")

def hex2str(hex):
    """
    Decodes a hex string into a regular string
    """
    return bytes.fromhex(hex[2:]).decode("utf-8")

def str2hex(str):
    """
    Encodes a string as a hex string
    """
    return "0x" + str.encode("utf-8").hex()

def ask_gpt(msg):
    # THIS REFERS TO THE MODEL NAME ON HUGGINGFACE OR PATH TO THE MODEL IN CARTESI MACHINE
    model_name_or_path = "cartesigpt/cartesigpt"

    model = AutoModelForCausalLM.from_pretrained(model_name_or_path,
                                             device_map="auto",
                                             local_files_only=True,
                                             trust_remote_code=False,
                                             revision="main")

    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, use_fast=True)

    prompt = msg
    prompt_template=f'''{prompt}'''

    print("\n\n*** Generate:")

    input_ids = tokenizer(prompt_template, return_tensors='pt').input_ids.cuda()
    output = model.generate(inputs=input_ids, temperature=0.7, do_sample=True, top_p=0.95, top_k=40, max_new_tokens=512)
    response = tokenizer.decode(output[0])
    print(response)

    return response

def handle_advance(data):

    logger.info(f"Received advance request data {data}")
    status = "accept"

    try:
        msg = int(hex2str(data["payload"]))
        logger.info(f"Received input: {msg}")

        # Evaluates expression
        result = ask_gpt(msg)

        # Emits notice with result
        logger.info(f"Adding notice with payload: '{result}'")
        response = requests.post(rollup_server + "/notice", json={"payload": str2hex(str(result))})
        logger.info(f"Received notice status {response.status_code} body {response.content}")

    except Exception as e:
        status = "reject"
        msg = f"Error processing data {data}\n{traceback.format_exc()}"
        logger.error(msg)
        response = requests.post(rollup_server + "/report", json={"payload": str2hex(msg)})
        logger.info(f"Received report status {response.status_code} body {response.content}")

    return status  

def handle_inspect(data):
    logger.info(f"Received inspect request data {data}")
    return "accept"

handlers = {
    "advance_state": handle_advance,
    "inspect_state": handle_inspect,
}

finish = {"status": "accept"}

while True:
    logger.info("Sending finish")
    response = requests.post(rollup_server + "/finish", json=finish)
    logger.info(f"Received finish status {response.status_code}")
    if response.status_code == 202:
        logger.info("No pending rollup request, trying again")
    else:
        rollup_request = response.json()
        data = rollup_request["data"]
        handler = handlers[rollup_request["request_type"]]
        finish["status"] = handler(rollup_request["data"])
