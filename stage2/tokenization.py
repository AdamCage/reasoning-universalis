"""Independent research BPE tokenizer; never advertised as the generator tokenizer."""
from collections import Counter
from measurement.core import digest, text_hash


class ResearchBPE:
    """Character-initial BPE with actual learned merges and exact Unicode offsets.

    This is an independently named analysis tokenizer. Model tokenizer identity
    remains unknown unless an independently authenticated model map is supplied.
    """
    def fit(self, texts, training_roots, merge_limit=32):
        if not texts or not training_roots or type(merge_limit) is not int or merge_limit < 0:
            raise ValueError('Empty or invalid tokenizer training')
        sequences = [list(t) for t in texts]
        self.merges = []
        for _ in range(merge_limit):
            counts = Counter(pair for seq in sequences for pair in zip(seq, seq[1:]))
            if not counts or max(counts.values()) < 2:
                break
            pair = min(counts, key=lambda p: (-counts[p], p))
            self.merges.append(list(pair))
            sequences = [self._merge(seq, pair) for seq in sequences]
        self.provenance = {'kind': 'independent_research_bpe', 'training_roots': sorted(set(training_roots)),
                           'training_text_digest': digest(texts), 'merge_limit': merge_limit}
        self.revision = digest({'algorithm': 'unicode-initial-bpe-v1', 'merges': self.merges,
                                'provenance': self.provenance})
        return self

    @staticmethod
    def _merge(seq, pair):
        output = []; i = 0
        while i < len(seq):
            if i+1 < len(seq) and (seq[i], seq[i+1]) == tuple(pair):
                output.append(seq[i]+seq[i+1]); i += 2
            else:
                output.append(seq[i]); i += 1
        return output

    def mapping(self, text):
        if not hasattr(self, 'revision'):
            raise ValueError('Tokenizer is not fitted')
        seq = list(text)
        for pair in self.merges:
            seq = self._merge(seq, pair)
        cursor = 0; offsets = []
        for token in seq:
            offsets.append([cursor, cursor+len(token)]); cursor += len(token)
        return {'text_sha256': text_hash(text), 'tokenizer_id': 'reasoning-universalis/research-bpe',
                'tokenizer_revision': self.revision, 'tokenizer_scope': 'independent_research_not_model',
                'offsets': offsets, 'token_texts': seq, 'training_provenance': self.provenance, 'merges': self.merges}
