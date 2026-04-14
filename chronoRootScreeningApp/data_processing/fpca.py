#!/usr/bin/env python3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from skfda import FDataGrid
from skfda.preprocessing.dim_reduction import FPCA
from skfda.representation.basis import MonomialBasis
import seaborn as sns
from scipy.stats import norm, mannwhitneyu
import os
import argparse
import sys
import json
plt.switch_backend('agg')

def load_config(path):
    """Load FPCA configuration from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def validate_config(config):
    """Validate FPCA configuration and set defaults."""
    required = ['file', 'xcol', 'ycols', 'output']
    missing = [k for k in required if k not in config]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    config.setdefault('normalize', False)
    config.setdefault('components', 2)
    config.setdefault('groupby', 'Experiment')
    config.setdefault('id_col', 'Plant_id')
    config.setdefault('figsize', [8, 16])
    config.setdefault('dpi', 300)

def run_fpca_analysis(config):
    """Run FPCA analysis based on provided arguments."""
    
    # Create output directory
    os.makedirs(config['output'], exist_ok=True)
    
    # If ".csv" in the file path, read the file as a CSV
    if ".csv" in config['file']:
        temporal_data_df = pd.read_csv(config['file'])
    elif ".tsv" in config['file']:
        temporal_data_df = pd.read_csv(config['file'], sep='\t')
    else:
        print("Unsupported file format. Please provide a CSV or TSV file.")
        sys.exit(1)

    # Convert group column to string
    temporal_data_df[config['groupby']] = temporal_data_df[config['groupby']].astype('str')
    temporal_data_df = temporal_data_df.sort_values(by=config['groupby'])
    
    # Create a unique identifier combining ID and group
    temporal_data_df[config['id_col']] = (temporal_data_df[config['id_col']].astype('str') +
                                    " (" + temporal_data_df[config['groupby']] + ")")
    
    # Get unique experiments/groups
    experiments = temporal_data_df[config['groupby']].unique()
    
    # Create a dictionary to get group ID for each plant
    get_expid = lambda plant_id: temporal_data_df.set_index(config['id_col'])[config['groupby']].to_dict()[plant_id]
    
    plt.ioff()
    
    # Process each Y column
    for magnitude in config['ycols']:
        print(f"Processing {magnitude}...")
        name = magnitude.split(" ")[0]
        
        # Create magnitude dictionary with pivoted data
        magnitude_data = temporal_data_df.pivot(
            columns=config['id_col'], 
            values=magnitude, 
            index=config['xcol']
        ).dropna()
        
        # Create figure
        plt.figure(figsize=tuple(config['figsize']))
        
        # Plot 1: Line plot with error bars
        plt.subplot(5, 2, 1)
        sns.lineplot(
            x=config['xcol'], 
            y=magnitude, 
            hue=config['groupby'], 
            data=temporal_data_df, 
            errorbar='se', 
            palette="tab10"
        )
        plt.title(magnitude)
        
        # Perform FPCA
        fpca = FPCA(n_components=config['components'], components_basis=MonomialBasis)
        fpc_values = fpca.fit_transform(FDataGrid(magnitude_data.transpose()))
        
        # Create DataFrame with FPC values
        fpc_df = pd.DataFrame(fpc_values).set_index(magnitude_data.columns)
        fpc_df.columns = [f"FPC{i}" for i in range(1, fpca.n_components+1)]
        fpc_df = fpc_df.reset_index()
        fpc_df[config['groupby']] = fpc_df[config['id_col']].apply(get_expid)
        
        # Inverse Rank Normalization if requested
        if config['normalize']:
            for j in range(1, fpca.n_components+1):
                fpc_df[f'FPC{j}_IRN'] = norm.ppf(fpc_df[f'FPC{j}'].rank() / (len(fpc_df) + 1))
        
        fpc_df = fpc_df.sort_values(by=config['groupby'])
        
        # Plot 2: Scatter PC1 vs PC2
        ax = plt.subplot(5, 2, 2)
        
        sns.scatterplot(
            data=fpc_df, 
            x='FPC1' + ('_IRN' if config['normalize'] else ''), 
            y='FPC2' + ('_IRN' if config['normalize'] else ''), 
            hue=config['groupby'], 
            palette="tab10", 
            s=100,
            ax=ax
        )
        ax.set_title('PC1 vs PC2')
        ax.set_xlabel('PC1' + (' (IRN)' if config['normalize'] else ''))
        ax.set_ylabel('PC2' + (' (IRN)' if config['normalize'] else ''))
        ax.legend(title=config['groupby'], bbox_to_anchor=(1.05, 1), loc='upper left')

        # Write statistical results
        with open(os.path.join(config['output'], f"{name}_stats.txt"), 'w') as f:
            f.write('Using Mann Whitney U test to compare different experiments\n')
            
            for fpc1 in range(1, config['components'] + 1):
                f.write(f'Stats for PC{fpc1}\n')
                
                for i in range(0, len(experiments)-1):
                    for j in range(i+1, len(experiments)):
                        exp1 = experiments[i]
                        exp2 = experiments[j]
                        p_value = mannwhitneyu(
                            x=fpc_df[f"FPC{fpc1}"][fpc_df[config['groupby']] == exp1],
                            y=fpc_df[f"FPC{fpc1}"][fpc_df[config['groupby']] == exp2],
                        )[1]
                        
                        # Write number of samples, mean and std deviation
                        mean1 = fpc_df[f"FPC{fpc1}"][fpc_df[config['groupby']] == exp1].mean()
                        std1 = fpc_df[f"FPC{fpc1}"][fpc_df[config['groupby']] == exp1].std()
                        n1 = fpc_df[fpc_df[config['groupby']] == exp1].shape[0]
                        mean2 = fpc_df[f"FPC{fpc1}"][fpc_df[config['groupby']] == exp2].mean()
                        std2 = fpc_df[f"FPC{fpc1}"][fpc_df[config['groupby']] == exp2].std()
                        n2 = fpc_df[fpc_df[config['groupby']] == exp2].shape[0]
                        f.write(f'Experiment {exp1}: n={n1}, mean={mean1:.4f}, std={std1:.4f}\n')
                        f.write(f'Experiment {exp2}: n={n2}, mean={mean2:.4f}, std={std2:.4f}\n')
                        
                        # Compare the p-value with the significance level
                        if p_value < 0.05:
                            f.write(f'Experiments {experiments[i]} and {experiments[j]} are significantly different. P-value: {p_value}\n')
                        else:
                            f.write(f'Experiments {experiments[i]} and {experiments[j]} are not significantly different. P-value: {p_value}\n')
                
                f.write('\n')
                
                # Box plots for each FPC
                ax = plt.subplot(5, 2, 1 + fpc1 * 2)
                fpc_col = f"FPC{fpc1}_IRN" if config['normalize'] else f"FPC{fpc1}"
                
                sns.boxplot(
                    data=fpc_df, 
                    x=config['groupby'], 
                    hue=config['groupby'], 
                    y=fpc_col, 
                    ax=ax, 
                    palette="tab10"
                )
                ax.set_title(f'PC{fpc1}. Explained Variance: {fpca.explained_variance_ratio_[fpc1-1]*100:.2f}%')
                
                # Interpretation plot for each PC
                ax = plt.subplot(5, 2, 1 + fpc1 * 2 + 1)
                
                N = 10
                quantiles = np.arange(N+1) / N
                z_quantiles = np.quantile(fpc_values, quantiles, axis=0)[1:-1]
                
                N = 8
                # Create a color palette
                palette = sns.color_palette("coolwarm", N+1)
                
                for i in range(z_quantiles.shape[0]):
                    z_value = z_quantiles[i, fpc1-1]
                    z = z_value * np.identity(config['components'])[:, (fpc1-1)]
                    curve = fpca.inverse_transform(z)
                    curve = [x[0] for x in curve.data_matrix[0]]
                    
                    # Get color for the current quantile
                    color = palette[i]
                    
                    # Plot the curve with the corresponding color
                    ax.plot(curve, color=color, label=f'Q {quantiles[i]:.2f}')
                
                ax.set_title(f"Interpretation of PC{fpc1}")
                ax.set_ylabel(magnitude)
                ax.set_xlabel(f"Time ({config['xcol'].split(' ')[-1].strip('()')})")
                
                # Create a legend with the quantiles
                handles = [plt.Line2D([0,1], [0,1], color=palette[i], lw=2) for i in range(N+1)][::-1]
                labels = [f'{z_quantiles[i, fpc1-1]:.2f}' for i in range(N+1)][::-1]
                ax.legend(
                    handles, 
                    labels, 
                    title=f'PC{fpc1} Value', 
                    bbox_to_anchor=(1.05, 1), 
                    loc='upper left'
                )
        
        # Save figure
        plt.tight_layout()
        plt.savefig(os.path.join(config['output'], f"{name}.png"), dpi=config['dpi'], bbox_inches='tight')
        plt.savefig(os.path.join(config['output'], f"{name}.svg"), dpi=config['dpi'], bbox_inches='tight')
        plt.close()
        plt.cla()
        plt.clf()
        
        # Create FPC scatter plots if there are 2 or more components
        if config['components'] >= 2:
            for i in range(1, config['components'] + 1):
                for j in range(i + 1, config['components'] + 1):
                    plt.figure(figsize=(8, 6))
                    fpc_i = f"FPC{i}{'_IRN' if config['normalize'] else ''}"
                    fpc_j = f"FPC{j}{'_IRN' if config['normalize'] else ''}"
                    
                    sns.scatterplot(data=fpc_df, x=fpc_i, y=fpc_j, hue=config['groupby'], palette="tab10", s=100)
                    plt.title(f'{magnitude} - PC{i} vs PC{j}', fontsize=14)
                    plt.xlabel(f'PC{i}', fontsize=12)
                    plt.ylabel(f'PC{j}', fontsize=12)
                    plt.legend(title=config['groupby'], bbox_to_anchor=(1.05, 1), loc='upper left')
                    plt.tight_layout()
                    
                    plt.savefig(os.path.join(config['output'], f"{name}_PC{i}_vs_PC{j}.png"), dpi=300, bbox_inches='tight')
                    plt.savefig(os.path.join(config['output'], f"{name}_PC{i}_vs_PC{j}.svg"), dpi=300, bbox_inches='tight')
                    plt.close()
                    plt.cla()
                    plt.clf()
        
        print(f"Saved plots for {magnitude} to {config['output']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Perform FPCA analysis from JSON configuration.')
    parser.add_argument('--config', required=True, help='Path to JSON configuration file')
    cli_args = parser.parse_args()
    config = load_config(cli_args.config)
    validate_config(config)
    run_fpca_analysis(config)
