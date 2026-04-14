import os
import argparse
import pandas as pd
import json
from data_processing.germination_analysis import GerminationAnalyzer
from data_processing.plant_analysis import PlantGrowthAnalyzer
from tracking.experiment_tracker import capture_run_logs, end_run, log_metrics, start_run

# ignore future warnings from pandas
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)


def load_config(path: str) -> dict:
    """Load report generation configuration from JSON."""
    with open(path, 'r') as f:
        return json.load(f)


def validate_config(config: dict) -> None:
    """Validate required report configuration fields."""
    if 'project_dir' not in config:
        raise ValueError("Missing required config field: project_dir")


def _as_bool(value) -> bool:
    """Parse bool-like config values deterministically."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    return bool(value)

def merge_analysis_files(project_dir: str, name_mapping_file: str = None) -> pd.DataFrame:
    """
    Merge all seeds.tsv files from different analyses into one dataframe.
    
    Args:
        project_dir: Project directory containing analysis folders
        name_mapping_file: Path to JSON file with group name mappings
    """
    analysis_dir = os.path.join(project_dir, 'analysis')
    all_data = []
    
    # Load name mapping if provided
    name_mapping = {}
    if name_mapping_file and os.path.exists(name_mapping_file):
        try:
            with open(name_mapping_file, 'r') as f:
                name_mapping = json.load(f)
        except Exception as e:
            print(f"Error loading name mapping: {str(e)}")
    
    # Get all analysis folders
    analyses = [d for d in os.listdir(analysis_dir)
                if os.path.isdir(os.path.join(analysis_dir, d))]
    
    for analysis_id in analyses:
        analysis_path = os.path.join(analysis_dir, analysis_id, 'seeds.tsv')
        metadata_path = os.path.join(analysis_dir, analysis_id, 'group_info.json')
        
        if os.path.exists(analysis_path):
            try:
                df = pd.read_csv(analysis_path, sep='\t')
                
                # make Group, UID string columns
                df['Group'] = df['Group'].astype(str)
                df['UID'] = df['UID'].astype(str)
                
                # Store original group names before mapping
                df['OriginalGroup'] = df['Group']
                
                # Apply name mapping if provided
                if name_mapping:
                    df['Group'] = df['Group'].map(lambda x: name_mapping.get(x, x))
                
                metadata = pd.read_json(metadata_path)
                metadata = metadata.rename(columns={
                    "group_names": "Group",
                    "seed_counts": "SeedCount"
                })
                
                # metadata group names should be string
                metadata['Group'] = metadata['Group'].astype(str)
                
                # Apply name mapping to metadata too
                if name_mapping:
                    metadata['OriginalGroup'] = metadata['Group']
                    metadata['Group'] = metadata['Group'].map(lambda x: name_mapping.get(x, x))
                
                df = df.merge(metadata, on='Group')
                df['Video'] = analysis_id
                
                all_data.append(df)
            except Exception as e:
                print(f"Error reading {analysis_path}: {str(e)}")
    
    if not all_data:
        raise ValueError("No valid seeds.tsv files found in any analysis folder")
    
    return pd.concat(all_data, ignore_index=True)

def run_pipeline(config: dict, run_path: str = None) -> None:
    """Run report generation from configuration dictionary."""
    project_dir = config['project_dir']
    dt = float(config.get('dt', 15))
    add_time_before_photo = int(config.get('add_time_before_photo', 0))
    germination_time_cut = int(config.get('germination_time_cut', 0))
    do_germination = _as_bool(config.get('do_germination', True))
    store_for_each_video = _as_bool(config.get('germination_each_video', False))
    do_plant_growth = _as_bool(config.get('do_plant_growth', True))
    do_fpca = _as_bool(config.get('do_fpca', False))
    fpca_components = int(config.get('fpca_components', 2))
    normalize_fpca = _as_bool(config.get('normalize_fpca', False))
    selected_metrics = config.get('selected_metrics', [])
    name_mapping = config.get('name_mapping')
    if isinstance(selected_metrics, str):
        selected_metrics = [m for m in selected_metrics.split(',') if m]

    results_dir = os.path.join(run_path, 'results') if run_path else os.path.join(project_dir, 'results')

    try:
        # Setup
        os.makedirs(results_dir, exist_ok=True)
        
        # Load and merge data with name mapping
        print("Merging analysis files...")
        combined_data = merge_analysis_files(project_dir, name_mapping)
        combined_data.to_csv(
            os.path.join(results_dir, 'Raw_Data.tsv'),
            sep='\t',
            index=False
        )
                
        # Run germination analysis
        if do_germination:
            print("Running germination analysis...")
            germ_analyzer = GerminationAnalyzer(
                data=combined_data,
                output_dir=results_dir,
                dt=dt,
                add_time_before_photo=add_time_before_photo,
                store_for_each_video=store_for_each_video,
                time_cut=germination_time_cut
            )
            germ_analyzer.analyze()
        
        # Run plant growth analysis
        if do_plant_growth:
            print("Analyzing plant growth...")
            plant_analyzer = PlantGrowthAnalyzer(
                data=combined_data,
                output_dir=results_dir,
                add_time_before_photo=add_time_before_photo,
                metrics=selected_metrics,
                do_fpca=do_fpca,
                fpca_components=fpca_components,
                fpca_normalize=normalize_fpca
            )
            plant_analyzer.analyze_all_parameters()

        print("Analysis complete!")
        print(f"Results saved in: {results_dir}")
                    
    except Exception as e:
        print(f"Error during post-processing: {str(e)}")
        raise


def main():
    parser = argparse.ArgumentParser(description='Post-process analysis results from JSON configuration')
    parser.add_argument('--config', required=True, help='Path to JSON configuration file')
    args = parser.parse_args()

    config = load_config(args.config)
    run_id, run_path = start_run(config)
    with capture_run_logs(os.path.join(run_path, 'logs.txt')):
        try:
            validate_config(config)
            run_pipeline(config, run_path=run_path)
            log_metrics(run_id, {'status': 'report_generated'}, run_path=run_path)
            end_run(run_id, 'completed', run_path=run_path)
            print(f"Report experiment saved in: {run_path}")
        except Exception as exc:
            end_run(run_id, 'failed', run_path=run_path, error=str(exc))
            raise

if __name__ == "__main__":
    main()