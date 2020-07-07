'''
Inference functionality for GPT2 finetuned model.

'''

import re
import json
import torch
from enum import Enum, unique
from transformers import (
    set_seed,
    AutoTokenizer,
    AutoModelWithLMHead
)

@unique
class ModelType(Enum):
    '''
    The type of GPT2 finetuned model.

    '''

    TIFU = 'tifu'
    WP = 'wp'
    PHC = 'phc'

@unique
class ModelDecodeFormat(Enum):
    '''
    The decoding format of the generated text.
        

    :cvar QUERY_ANSWER:
        This format can be thought of a pair of strings (referred to 
        as the query and answer respectively) where the answer is a 
        mapping of the query into some other translation space. For 
        example, the query might be a sentence in English and the answer
        might be the same sentence translated to German.

        For example, in the case of Reddit post text generation, the 
        query is the  title of the post (such as a writingprompt) and
        the answer is  the corresponding post selftext or comment
        (such as a story written from the prompt).

    :cvar PHC:
        This format is specifically for pornhub comments, where the model
        outputs text conditioned on the number of likes and author username.

    '''

    QUERY_ANSWER = 'qa'
    PHC = 'phc'

class RawRecord:
    '''
    Text generated by a GPT2 language model which has been split up into
    groups of data (match groups).

    '''

    def __init__(self, groups, raw_text):
        '''
        Initializes an instance of :class:`RawRecord`.

        :param groups:
            A dictionary mapping the name of each group to its data.
        :param raw_text:
            The raw output of the model, containing all special tokens.

        '''

        self.groups = groups
        self.raw_text = raw_text

def _init_fp16(*args, opt_level='O1'):
    '''
    Initializes the specified arguments with Automated
    Mixed Precision (AMP) using NVIDIA Apex.

    '''

    try:
        from apex import amp
    except ImportError:
        raise ImportError('Please install apex from https://www.github.com/nvidia/apex to use fp16 inference.')

    return amp.initialize(*args, opt_level=opt_level)

def _verify_special_tokens(tokenizer, **kwargs):
    '''
    Verifies that the specified special tokens (given as keyword arguments)
    are flagged as additional special tokens in the given tokenzier.

    '''
    
    special_tokens = set(tokenizer.additional_special_tokens)
    for token_name, token_value in kwargs.items():
        if token_value in special_tokens: continue
        raise ValueError('The {} token (\'{}\') is not marked as a special token.'.format(
            token_name, token_value
        ))

def load_model(model_path, tokenizer_path=None, no_cuda=False):
    '''
    Loads a pretrained language model and tokenzier.
    
    :param model_path:
        The name of standard pretrained model or a path
        to a checkpoint for weights initialization.
    :param tokenizer_path:
        Optional pretrained tokenizer name or path if not
        the same as the model checkpoint path. If both None,
        a new tokenizer will be initialized.
    :param no_cuda:
        Disable CUDA devices even when they are available. Defaults to False.
    :returns:
        A :class:`transformers.PreTrainedModel` and a
        :class:`transformers.PreTrainedTokenizer`.

    '''

    if tokenizer_path:
        tokenizer = AutoTokenizer.from_pretrained(tokenizer_path)
    elif model_path:
        tokenizer = AutoTokenizer.from_pretrained(model_path)
    else:
        raise ValueError(
            'Instantiating a new tokenizer from scratch is not support; however, it can be done from another script.'
            'Use the tokenizer_path argument to provide it with the location of the script to load the tokenizer.'
        )
    
    model = AutoModelWithLMHead.from_pretrained(model_path)

     # Setup device
    device = torch.device('cuda' if torch.cuda.is_available() and not no_cuda else 'cpu')
    model.to(device)

    return model, tokenizer

def generate(model, tokenizer, decode_format, prompt=None, samples=1, top_k=300,
             top_p=1, num_return_sequences=10, max_iterations=10, min_length=250,
             max_length=1024, translate_token='<|eq_tok|>', end_of_likes_token='<|eol|>',
             fp16=False, fp16_opt_level='O1', no_duplicates=False):
    '''
    Generate text from a model with a language modelling head.

    :param model:
        A :class:`transformers.PreTrainedModel` to use for inference.
    :param tokenizer:
        A :class:`transformers.PreTrainedTokenizer` to use to encode
        input sequences to token and to decode output sequences to text.
    :param decode_format:
        A :class:`ModelDecodeFormat` representing the format of the model output.
    :param prompt:
        A prompt for the model. Defaults to None, meaning no prompt is given.
    :param samples:
        The number of samples to generate. Defaults to 1.
    :param top_k:
        The number of highest probability vocabulary tokens to keep for top-k-filtering.
        Between 1 and infinity. Default to 300.
    :param top_p:
        The cumulative probability of parameter highest probability vocabulary tokens to
        keep for nucleus sampling. Must be between 0 and 1. Default to 1.
    :param num_return_sequences:
        The number of sequences to return per iteration. Defaults to 10.
    :param max_iterations:
        Maximum number of iterations. Defaults to 10.
        
        If -1, there is no maximum number of iterations; the function will wait until all
        samples have been generated. This can potentially be very slow and thread-blocking.
    :param min_length:
        Minimum number of tokens to generate in a single iteration. Defaults to 250 tokens.
    :param max_length:
        Maximum number of tokens to generate in a single iteration. Defaults to 1024 tokens.
    :param translate_token:
        The query/answer separator token (translation separator token). Used for both 
        :var:`ModelDecodeFormat.QUERY_ANSWER` and :var:`ModelDecodeFormat.PHC` decoding.
    :param end_of_likes_token:
        The special token specifying the end of likes. Used for :var:`ModelDecodeFormat.PHC` decoding.
    :param fp16:
        Use 16-bit (mixed) precision floats (note: requires NVIDIA Apex!). Defaults to False.
    :param fp16_opt_level:
        Apex AMP optimization level. See https://nvidia.github.io/apex/amp.html. Defaults to O1.
    :param no_duplicates:
        Don't generate any duplicate records. Defaults to False.
    :returns:
        A list of :class:`RawRecord` objects.

    '''

    if fp16:
        model = _init_fp16(model, opt_levl=fp16_opt_level)

    provided_special_tokens = {
        'translate': translate_token,
    }

    if decode_format == ModelDecodeFormat.PHC:
        provided_special_tokens['end_of_likes'] = end_of_likes_token

    _verify_special_tokens(tokenizer,  **provided_special_tokens)   

    # A mapping defining the regex pattern to use to split
    # the model output into groups of data based on the decode format.
    DECODE_REGEX_MAPPING = {
        ModelDecodeFormat.QUERY_ANSWER: (
            f'^{re.escape(tokenizer.bos_token)}(?P<prompt>.+?)'
            f'(?:{re.escape(translate_token)}(?P<response>.+?))*'
            f'{re.escape(tokenizer.eos_token)}'
        ),
        ModelDecodeFormat.PHC: (
            f'^{re.escape(tokenizer.bos_token)}(?P<likes>.+?)'
            f'(?:{re.escape(end_of_likes_token)}(?P<author>.+?))*'
            f'(?:{re.escape(translate_token)}(?P<comment_body>.+?))*'
            f'{re.escape(tokenizer.eos_token)}'
        )
    }

    if decode_format not in DECODE_REGEX_MAPPING:
        ValueError('{} is invalid. Must be one of: {}.'.format(
            decode_format, list(DECODE_REGEX_MAPPING.keys())
        ))
    
    decode_regex = re.compile(DECODE_REGEX_MAPPING[decode_format], flags=re.MULTILINE | re.DOTALL)

    # If no prompt is specified, the default is the BOS token.
    prompt = prompt or tokenizer.bos_token
    # Encode the prompt using the tokenizer
    prompt_ids = tokenizer.encode(prompt, return_tensors='pt').to(model.device)

    results = []
    visited = set()
    current_iteration = 0
    
    while len(results) < samples:
        if max_iterations != -1 and current_iteration > max_iterations: break

        current_iteration += 1
        remaining_samples = samples - len(results)
        # Multiply by some 'arbitrary' scale factor to pad the next attempt in case there are
        # any failed attempts. We use 1.5 as an approximation under the assumption that 50% of
        # the samples in iteration are failed (this is an overestimation for safety).
        num_return_sequences = min(int(remaining_samples * 1.5), num_return_sequences)
        output = model.generate(
            prompt_ids,
            bos_token_id=tokenizer.bos_token_id,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.pad_token_id,
            top_k=top_k, top_p=top_p,
            num_return_sequences=num_return_sequences,
            min_length=min_length, max_length=max_length,
            do_sample=True
        )

        for i in range(output.size()[0]):
            if len(results) >= samples: break

            raw_text = tokenizer.decode(output[i, :].tolist())
            if decode_format == ModelDecodeFormat.PHC:
                # Filter out for pornhub links contained in the comment.
                # Comments that contain links are often not very interesting (just advertisement).
                urls = re.findall(r'(?P<url>(https?://)?.*pornhub\.com*[^\s]+)', decoded)
                if len(urls) > 0: continue
            
            match = decode_regex.match(raw_text)
            # Check if the decode regex matched the decoded string
            if not match: continue

            if decode_format == ModelDecodeFormat.QUERY_ANSWER:
                groups = {
                    'prompt': match.group('prompt'),
                    'response': match.group('response')
                }
            elif decode_format == ModelDecodeFormat.PHC:
                groups = {
                    'likes': match.group('likes'),
                    'author': match.group('author'),
                    'comment_body': match.group('comment_body'),
                }

            # Check if generated sequence has missing matching groups
            if any(value is None for value in groups.values()): continue
            # Strip all match groups of trailing whitespace
            groups = {key: value.strip() for key, value in groups.items()}
            if no_duplicates:
                # Convert the groups dict to JSON and use it as a unique identifier
                groups_id = json.dumps(groups, sort_keys=True)
                if groups_id in visited: continue
                visited.add(groups_id)

            results.append(RawRecord(groups, raw_text))

    return results