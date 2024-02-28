import torch
import torch.nn as nn


# TODO language_detection block oluşturuyoruz ki dil algılama sağlanabilsin


# TODO Training arguments oluşturuyoruz ki kodları güvenliği ve temizliği için
class TrainArgumentsForOurModel:
    def __init__(
        self,
        embed_size=512,
        heads=8,
        dropout=0,
        forward_expansion=4,
        src_vocab_size=None,
        trg_vocab_size=None,
        src_pad_idx=0,
        trg_pad_idx=0,
        num_layers=6,
        device="cpu",
        max_length=100,
        norm_activite_func="LayerNorm",
    ):
        self.embed_size = embed_size
        self.heads = heads
        self.dropout = dropout
        self.forward_expansion = forward_expansion
        self.norm_activite_func = norm_activite_func
        self.src_vocab_size = src_vocab_size
        self.trg_vocab_size = trg_vocab_size
        self.src_pad_idx = src_pad_idx
        self.trg_pad_idx = trg_pad_idx
        self.num_layers = num_layers
        self.device = device
        self.max_length = max_length


class AttentionBlock(nn.Module):
    def __init__(self, embed_size, heads):
        super(AttentionBlock, self).__init__()
        self.embed_size = embed_size
        self.heads = heads
        self.head_dim = embed_size // heads

        # Başlıklara göre gömülü boyutlarının uygun olup olmadığını kontrol edin
        assert (
            self.head_dim * heads == embed_size
        ), "Gömülü değer belirtilen başlıklara bölünebilmeli"

        # Anahtar, değer ve sorgu matrislerini oluşturun
        self.values = nn.Linear(embed_size, embed_size)
        self.keys = nn.Linear(embed_size, embed_size)
        self.queries = nn.Linear(embed_size, embed_size)
        self.fc_out = nn.Linear(embed_size, embed_size)

    def forward(self, values, keys, query, mask):
        N = query.shape[0]
        value_len, key_len, query_len = (
            values.shape[1],
            keys.shape[1],
            query.shape[1],
        )

        # Değerlerin boyutunu alın
        values = self.values(values)
        keys = self.keys(keys)
        queries = self.queries(query)

        # Boyutları yeniden şekillendirin
        values = values.reshape(N, value_len, self.heads, self.head_dim)
        keys = keys.reshape(N, key_len, self.heads, self.head_dim)
        queries = queries.reshape(N, query_len, self.heads, self.head_dim)

        # Sorgu ve anahtar arasındaki dikkat ağırlıklarını hesaplayın
        energy = torch.einsum("nqhd,nkhd->nhqk", [queries, keys])

        # Maskeyi uygulayın (varsa)
        if mask is not None:
            energy = energy.masked_fill(mask == 0, float("-1e20"))

        # Dikkat ağırlıklarını softmax ile normalize edin
        attention = torch.softmax(energy / (self.embed_size ** (1 / 2)), dim=3)

        # Ağırlıklı değerlerle birleştirin
        out = torch.einsum("nhql,nlhd->nqhd", [attention, values]).reshape(
            N, query_len, self.heads * self.head_dim
        )

        # Çıktıyı tam bağlı katmana gönderin
        out = self.fc_out(out)

        return out


class Tanh(nn.Module):
    def forward(self, x):
        return 0.5 * x * (1 + torch.tanh(0.79788456 * (x + 0.044715 * x**3)))


class TransformerBlock(nn.Module):
    def __init__(self, embed_size, heads, dropout, forward_expansion):
        super(TransformerBlock, self).__init__()
        self.attention = AttentionBlock(embed_size, heads)
        self.norm1 = nn.LayerNorm(embed_size)
        self.norm2 = nn.LayerNorm(embed_size)
        self.feed_forward = nn.Sequential(
            nn.Linear(embed_size, forward_expansion * embed_size),
            nn.ReLU(),
            nn.Linear(forward_expansion * embed_size, embed_size),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, value, key, query, mask):
        # Dikkat mekanizmasını ve katman normalizasyonunu uygulayın
        attention = self.attention(value, key, query, mask)
        x = self.dropout(self.norm1(attention + query))
        forward = self.feed_forward(x)
        out = self.dropout(self.norm2(forward + x))
        return out


class Encoder(nn.Module):
    def __init__(
        self,
        src_vocab_size,
        embed_size,
        num_layers,
        heads,
        device,
        forward_expansion,
        dropout,
        max_length,
    ):

        super(Encoder, self).__init__()
        self.embed_size = embed_size
        self.device = device
        self.word_embedding = nn.Embedding(src_vocab_size, embed_size)
        self.position_embedding = nn.Embedding(max_length, embed_size)

        self.layers = nn.ModuleList(
            [
                TransformerBlock(
                    embed_size,
                    heads,
                    dropout=dropout,
                    forward_expansion=forward_expansion,
                )
                for _ in range(num_layers)
            ]
        )

        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask):
        N, seq_length = x.shape
        positions = torch.arange(0, seq_length).expand(N, seq_length).to(self.device)
        out = self.dropout(
            (self.word_embedding(x) + self.position_embedding(positions))
        )

        # Tüm katmanları geçişli olarak uygulayın
        for layer in self.layers:
            out = layer(out, out, out, mask)

        return out


class DecoderBlock(nn.Module):
    def __init__(
        self,
        embed_size,
        heads,
        forward_expansion,
        dropout,
        device,
        norm_activite_func="LayerNorm",
    ):
        super(DecoderBlock, self).__init__()
        self.norm = nn.LayerNorm(embed_size)
        self.attention = AttentionBlock(embed_size, heads=heads)
        self.transformer_block = TransformerBlock(
            embed_size,
            heads,
            dropout,
            forward_expansion,
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, value, key, src_mask, trg_mask):
        attention = self.attention(x, x, x, trg_mask)
        query = self.dropout(self.norm(attention + x))
        out = self.transformer_block(value, key, query, src_mask)
        return out


class Decoder(nn.Module):
    def __init__(
        self,
        trg_vocab_size,
        embed_size,
        num_layers,
        heads,
        forward_expansion,
        dropout,
        device,
        max_length,
        norm_activite_func,
    ):
        super(Decoder, self).__init__()
        self.device = device
        self.word_embedding = nn.Embedding(trg_vocab_size, embed_size)
        self.position_embedding = nn.Embedding(max_length, embed_size)

        self.layers = nn.ModuleList(
            [
                DecoderBlock(
                    embed_size,
                    heads,
                    forward_expansion,
                    dropout,
                    device,
                )
                for _ in range(num_layers)
            ]
        )
        self.fc_out = nn.Linear(embed_size, trg_vocab_size)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, enc_out, src_mask, trg_mask):
        N, seq_length = x.shape
        positions = torch.arange(0, seq_length).expand(N, seq_length).to(self.device)
        x = self.dropout((self.word_embedding(x) + self.position_embedding(positions)))

        for layer in self.layers:
            x = layer(x, enc_out, enc_out, src_mask, trg_mask)

        out = self.fc_out(x)

        return out


class Transformer(nn.Module):
    def __init__(self, arguments: TrainArgumentsForOurModel):

        super(Transformer, self).__init__()

        self.encoder = Encoder(
            arguments.src_vocab_size,
            arguments.embed_size,
            arguments.num_layers,
            arguments.heads,
            arguments.device,
            arguments.forward_expansion,
            arguments.dropout,
            arguments.max_length,
        )

        self.decoder = Decoder(
            arguments.trg_vocab_size,
            arguments.embed_size,
            arguments.num_layers,
            arguments.heads,
            arguments.forward_expansion,
            arguments.dropout,
            arguments.device,
            arguments.max_length,
            arguments.norm_activite_func,
        )

        self.src_pad_idx = arguments.src_pad_idx
        self.trg_pad_idx = arguments.trg_pad_idx
        self.device = arguments.device

    def make_src_mask(self, src):
        src_mask = (src != self.src_pad_idx).unsqueeze(1).unsqueeze(2)
        return src_mask.to(self.device)

    def make_trg_mask(self, trg):
        N, trg_len = trg.shape
        trg_mask = torch.tril(torch.ones((trg_len, trg_len))).expand(
            N, 1, trg_len, trg_len
        )

        return trg_mask.to(self.device)

    def forward(self, src, trg):
        src_mask = self.make_src_mask(src)
        trg_mask = self.make_trg_mask(trg)
        enc_src = self.encoder(src, src_mask)
        out = self.decoder(trg, enc_src, src_mask, trg_mask)
        return out


if __name__ == "__main__":
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(device)

    x = torch.tensor([[1, 5, 6, 4, 3, 9, 5, 2, 0], [1, 8, 7, 3, 4, 5, 6, 7, 2]]).to(
        device
    )
    trg = torch.tensor([[1, 7, 4, 3, 5, 9, 2, 0], [1, 5, 6, 2, 4, 7, 6, 2]]).to(device)

    src_pad_idx = 0
    trg_pad_idx = 0
    src_vocab_size = 10
    trg_vocab_size = 10
    trainArguments = TrainArgumentsForOurModel(
        embed_size=512,
        heads=8,
        dropout=0,
        forward_expansion=4,
        src_vocab_size=src_vocab_size,
        trg_vocab_size=trg_vocab_size,
        src_pad_idx=src_pad_idx,
        trg_pad_idx=trg_pad_idx,
        num_layers=6,
        device=device,
        max_length=100,
        norm_activite_func="tanh",
    )
    model = Transformer(trainArguments).to(device)
    out = model(x, trg[:, :-1])
    print(out.shape)
