import torch
import torch.nn as nn
from tokenizers import Tokenizer
from Transformer import model
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics.pairwise import cosine_similarity
import seaborn as sns
from tqdm import tqdm
import os
from torch.utils.data import DataLoader, Dataset
import torch.nn.utils.rnn as rnn_utils

# Check if CUDA is available
device = torch.device("cuda" if torch.cuda.is_available() else 'cpu')

# Initialize the transformer model
def initialize_model(tokenizer_path="bpe_token.json", d_model=256, src_leq_len=512):
    tokenizer = Tokenizer.from_file(tokenizer_path)
    src_vocab_size = tokenizer.get_vocab_size()
    tgt_vocab_size = src_vocab_size
    
    transformer_model = model.build_transformer(
        src_vocab_size, tgt_vocab_size, src_leq_len=src_leq_len, tgt_seq_len=src_leq_len, d_model=d_model
    ).to(device)
    
    return transformer_model, tokenizer

# Custom dataset class
class CustomDataset(Dataset):
    def __init__(self, tokenized_inputs, tokenized_targets=None):
        self.inputs = tokenized_inputs
        self.targets = tokenized_targets

    def __len__(self):
        return len(self.inputs)

    def __getitem__(self, idx):
        input_ids = self.inputs[idx]
        if self.targets is not None:
            target_ids = self.targets[idx]
            return {"input_ids": torch.tensor(input_ids, dtype=torch.long), 
                    "target_ids": torch.tensor(target_ids, dtype=torch.long)}
        return {"input_ids": torch.tensor(input_ids, dtype=torch.long)}

# Define the collate function
def collate_fn(batch):
    input_ids = [item['input_ids'] for item in batch]
    target_ids = [item['target_ids'] for item in batch]

    input_ids_padded = rnn_utils.pad_sequence(input_ids, batch_first=True, padding_value=0)
    target_ids_padded = rnn_utils.pad_sequence(target_ids, batch_first=True, padding_value=0)

    return {"input_ids": input_ids_padded, "target_ids": target_ids_padded}

# Tokenize data
def tokenize_data(tokenizer, directory, batch_size=128):
    encoded_input = []
    encoded_target = []

    def read_files_in_chunks(directory, chunk_size=10000):
        file_list = [os.path.join(directory, file) for file in os.listdir(directory) if file.endswith(".txt")]
        for file_name in file_list:
            with open(file_name, "r", encoding="utf-8", errors="ignore") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

    for chunk in read_files_in_chunks(directory):
        encoded_input.extend(tokenizer.encode(chunk).ids)
        encoded_target.extend(tokenizer.encode(chunk).ids)

    input_ids_batches = [encoded_input[i:i + batch_size] for i in range(0, len(encoded_input), batch_size)]
    target_ids_batches = [encoded_target[i:i + batch_size] for i in range(0, len(encoded_target), batch_size)]

    return input_ids_batches, target_ids_batches

# Fine-tune model with Early Stopping
import torch
import torch.nn as nn
from tqdm import tqdm

# Save the model
def save_model(model, path="LuminaLM_01.pth"):
    torch.save(model.state_dict(), path)
    print(f"Model saved to {path}")

# Fine-tune model with early stopping and model saving logic
def fine_tune_model_with_early_stopping(
    model, train_loader, val_loader, epochs=5, lr=5e-5, patience=3
):
    model.train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler()

    loss_values, accuracy_values, perplexity_values, val_loss_values, val_accuracy_values = [], [], [], [], []

    best_val_loss = float('inf')  # Initialize with high value
    patience_counter = 0  # Initialize patience counter

    for epoch in range(epochs):
        total_loss = 0
        correct_predictions = 0
        total_predictions = 0
        total_perplexity = 0

        model.train()
        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}/{epochs}"):
            optimizer.zero_grad()
            input_ids = batch['input_ids'].to(device)
            target_ids = batch['target_ids'].to(device)

            with torch.amp.autocast(device_type='cuda'):
                outputs = model(input_ids, target_ids)
                loss = criterion(outputs.view(-1, outputs.size(-1)), target_ids.view(-1))
                perplexity = torch.exp(loss)
                total_perplexity += perplexity.item()

            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            total_loss += loss.item()
            _, predicted = torch.max(outputs, -1)
            correct_predictions += (predicted == target_ids).sum().item()
            total_predictions += target_ids.numel()

        avg_loss = total_loss / len(train_loader)
        accuracy = correct_predictions / total_predictions
        avg_perplexity = total_perplexity / len(train_loader)

        loss_values.append(avg_loss)
        accuracy_values.append(accuracy)
        perplexity_values.append(avg_perplexity)

        # Validation step
        val_loss, val_accuracy = validate_model(model, val_loader, criterion)
        val_loss_values.append(val_loss)
        val_accuracy_values.append(val_accuracy)

        # Check if the validation loss improved
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            print(f"Validation loss improved to: {val_loss:.4f}")
        else:
            patience_counter += 1

        # Save the model after the 4th epoch
        if epoch == 3:
            save_model(model, "best_model_after_4th_epoch.pth")
            print(f"Model saved after the 4th epoch with validation loss: {val_loss:.4f}")
        
        # Update model after 5th epoch, unless early stopping
        elif epoch > 3 and patience_counter < patience:
            save_model(model, f"best_model_epoch_{epoch+1}.pth")
            print(f"Model updated after epoch {epoch+1} with validation loss: {val_loss:.4f}")

        # Early stopping
        if patience_counter >= patience:
            print("Early stopping triggered. No improvement in validation loss.")
            break

    return loss_values, accuracy_values, perplexity_values, val_loss_values, val_accuracy_values

# Validation function (unchanged)
def validate_model(model, val_loader, criterion):
    model.eval()
    total_val_loss = 0
    correct_val_predictions = 0
    total_val_predictions = 0

    with torch.no_grad():
        for batch in val_loader:
            input_ids = batch['input_ids'].to(device)
            target_ids = batch['target_ids'].to(device)

            outputs = model(input_ids, target_ids)
            loss = criterion(outputs.view(-1, outputs.size(-1)), target_ids.view(-1))

            total_val_loss += loss.item()
            _, predicted = torch.max(outputs, -1)
            correct_val_predictions += (predicted == target_ids).sum().item()
            total_val_predictions += target_ids.numel()

    avg_val_loss = total_val_loss / len(val_loader)
    val_accuracy = correct_val_predictions / total_val_predictions

    return avg_val_loss, val_accuracy

# Generate embeddings post-training
def generate_embeddings(model, input_ids_batches):
    model.eval()
    all_embeddings = []
    with tqdm(total=len(input_ids_batches), desc="Generating Embeddings") as pbar_batches:
        for batch in input_ids_batches:
            input_ids = torch.tensor([batch], dtype=torch.long).to(device)

            # Correct mask creation to match attention dimensions
            src_mask = (input_ids != 0).unsqueeze(1).to(device)
            
            with torch.no_grad():
                embeddings = model.encode(input_ids, src_mask)
            all_embeddings.append(embeddings.squeeze(0).detach().cpu())
            pbar_batches.update(1)

    all_embeddings_tensor = torch.cat(all_embeddings, dim=0)
    return all_embeddings_tensor

# PCA and t-SNE plotting (with sample size)
def plot_embeddings(embeddings_np, method="PCA", sample_size=500000):
    sample_indices = np.random.choice(embeddings_np.shape[0], sample_size, replace=False)
    sampled_embeddings = embeddings_np[sample_indices]

    if method == "PCA":
        pca = PCA(n_components=3)
        reduced_embeddings = pca.fit_transform(sampled_embeddings)
        title = "3D PCA Projection"
    elif method == "t-SNE":
        tsne = TSNE(n_components=3, random_state=42, perplexity=30, n_iter=300)
        reduced_embeddings = tsne.fit_transform(sampled_embeddings)
        title = "3D t-SNE Projection"
    
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.scatter(reduced_embeddings[:, 0], reduced_embeddings[:, 1], reduced_embeddings[:, 2], alpha=0.5)
    ax.set_title(title)
    if title == '3D PCA Projection':
        plt.savefig('3D_PCA_Projection.png')
    if title == '3D t-SNE Projection':
        plt.savefig('3D_tSNE_Projection.png')
    plt.show()

# Cosine Similarity Matrix (Sampled)
def calculate_sampled_cosine_similarity(embeddings_np, sample_size=500000):
    sample_indices = np.random.choice(embeddings_np.shape[0], sample_size, replace=False)
    sampled_embeddings = embeddings_np[sample_indices]
    cos_sim_matrix = cosine_similarity(sampled_embeddings)
    sns.heatmap(cos_sim_matrix, cmap='viridis', xticklabels=False, yticklabels=False)
    plt.title('Cosine Similarity Matrix (Sampled)')
    plt.savefig('Cosine_Similarity_Matrix_(Sampled).png')
    plt.show()

# Token frequency for top tokens
def get_top_tokens(tokenizer, tokenized_data, top_n=10):
    from collections import Counter
    tokens = [token for batch in tokenized_data for token in batch]
    token_counts = Counter(tokens)
    sorted_tokens = token_counts.most_common(top_n)
    return sorted_tokens

# Load the model
def load_model(model, path="LuminaLM.pth"):
    model.load_state_dict(torch.load(path))
    model.eval()
    print(f"Model loaded from {path}")
