"""Functions to help clean & normalize business names.

See http://www.unicode.org/reports/tr15/#Normalization_Forms_Table for details
on Unicode normalization and the NFKD normalization used here.

Basic usage:

>> terms = prepare_default_terms()
>> basename("Daddy & Sons, Ltd.", terms, prefix=True, middle=True, suffix=True)
Daddy & Sons

"""

import functools
import operator
import ahocorasick
import heapq
import re
import unicodedata
from .termdata import terms_by_type, terms_by_country
from .non_nfkd_map import NON_NFKD_MAP

tail_removal_rexp = re.compile(r"[^\.\w]+$", flags=re.UNICODE)


def get_unique_terms():
    "retrieve all unique terms from termdata definitions"
    ts = functools.reduce(operator.iconcat, terms_by_type.values(), [])
    cs = functools.reduce(operator.iconcat, terms_by_country.values(), [])
    return set(ts + cs)


# Create dictionary mapping instead
TRANSLATION_TABLE = str.maketrans({
    i: '' if unicodedata.combining(chr(i)) else chr(i)
    for i in range(0x80, 0x10ffff)
})

def remove_accents_fast(text):
    return text.casefold().translate(TRANSLATION_TABLE)

def remove_accents(t):
    """based on https://stackoverflow.com/a/51230541"""
    nfkd_form = unicodedata.normalize('NFKD', t.casefold())
    return ''.join(
        NON_NFKD_MAP[c]
            if c in NON_NFKD_MAP
        else c
            for part in nfkd_form for c in part
            if unicodedata.category(part) != 'Mn'
        )


def strip_punct(t):
    return t.replace(".", "").replace(",", "").replace("-", "")


def normalize_terms(terms):
    "normalize terms"
    return (strip_punct(remove_accents(t)) for t in terms)


def strip_tail(name):
    "get rid of all trailing non-letter symbols except the dot"
    while name and not name[-1].isalnum() and name[-1] != ".":
        name = name[:-1]
    return name


def normalized(text):
    "caseless Unicode normalization"
    ## return remove_accents(text)
    return remove_accents_fast(text)


def prepare_default_terms():
    "construct an optimized term structure for basename extraction"
    terms = get_unique_terms()
    nterms = normalize_terms(terms)
    ntermparts = (t.split() for t in nterms)
    # make sure that the result is deterministic, sort terms descending by number of tokens, ascending by names
    sntermparts = sorted(ntermparts, key=lambda x: (-len(x), x))
    return [(len(tp), tp) for tp in sntermparts]


def custom_basename_old(name, terms, suffix=True, prefix=False, middle=False, **kwargs):
    "return cleaned base version of the business name"

    name = strip_tail(name)
    nparts = name.split()
    nname = normalized(name)
    nnparts = list(map(strip_punct, nname.split()))
    nnsize = len(nnparts)

    if suffix:
        for idx, (termsize, termparts) in enumerate(terms):
            if nnparts[-termsize:] == termparts:
                del nnparts[-termsize:]
                del nparts[-termsize:]

    if prefix:
        for termsize, termparts in terms:
            if nnparts[:termsize] == termparts:
                del nnparts[:termsize]
                del nparts[:termsize]

    if middle:
        for termsize, termparts in terms:
            if termsize > 1:
                sizediff = nnsize - termsize
                if sizediff > 1:
                    for i in range(0, nnsize-termsize+1):
                        if termparts == nnparts[i:i+termsize]:
                            del nnparts[i:i+termsize]
                            del nparts[i:i+termsize]
            else:
                if termparts[0] in nnparts[1:-1]:
                    idx = nnparts[1:-1].index(termparts[0])
                    del nnparts[idx+1]
                    del nparts[idx+1]


    return strip_tail(" ".join(nparts))


def build_automaton(terms):
    "build Aho-Corasick automaton for terms"
    a = ahocorasick.Automaton()
    for idx, (_, _term) in enumerate(terms):
        term = " ".join(_term)
        a.add_word(term, (idx, term))
    a.make_automaton()
    return a

def custom_basename(
        name, 
        terms,
        suffix=True, 
        prefix=False, 
        middle=False, 
        **kwargs,
        ):
    "return cleaned base version of the business name"
    global global_automaton
    if global_automaton is None:
        global_automaton = build_automaton(terms)

    name = strip_tail(name)

    ## Get non-alphanumeric tokens for later insertion.
    non_alphanum_toks = []
    nparts = []
    for idx, tok in enumerate(name.split()):
        stripped_tok = strip_punct(tok)
        if stripped_tok == "":
            non_alphanum_toks.append((idx, tok))

        nparts.append(tok)

    nname = normalized(strip_punct(name))

    matches = []
    for end_idx, (priority_idx, match) in global_automaton.iter(nname):
        start_idx = end_idx - len(match) + 1

        cond_1 = (not nname[max(0, start_idx - 1)].isalnum()) or (start_idx == 0)
        cond_2 = (end_idx == len(nname) - 1) or (not nname[min(len(nname) - 1, end_idx + 1)].isalnum())

        if middle:
            if not prefix:
                cond_2 &= (start_idx != 0)
            if not suffix:
                cond_2 &= (end_idx != len(nname) - 1)
        else:
            cond_2 &= (((start_idx == 0) and prefix) or ((end_idx == len(nname) - 1) and suffix))

        if cond_1 and cond_2:
            heapq.heappush(matches, (priority_idx, (start_idx, end_idx, match)))

    if len(matches) == 0:
        return name

    char_array = list(nname)
    for _ in range(len(matches)):
        _, (start_idx, end_idx, match) = heapq.heappop(matches)

        ## Period should be guaranteed not to be there from strip_punct.
        char_array[start_idx:end_idx + 1] = "".join(
                "." if x != " " else x for x in match
                )

    tokens = "".join(char_array).split()
    for idx, non_alphanum_tok in non_alphanum_toks:
        tokens.insert(idx, non_alphanum_tok)

    final = []
    for idx, x in enumerate(tokens):
        if len(x.replace(".", "")) != 0:
            final.append(nparts[idx])

    return strip_tail(" ".join(final))

# convenience for most common use cases that don't parametrize base name extraction
basename_old = functools.partial(custom_basename_old, terms=prepare_default_terms())
global_automaton = None
basename = functools.partial(custom_basename, terms=prepare_default_terms())
