"""NEAT configuration builder extracted from NEAT/main.py lines 341-421.

This module provides functions to create NEAT configuration files
programmatically or load from file.

Original source: NEAT/main.py lines 341-421
"""

import os
from dataclasses import dataclass
from typing import Any

import neat

DEFAULT_CONFIG = """
[NEAT]
fitness_criterion     = max
fitness_threshold     = 100000
pop_size              = 150
reset_on_extinction   = False
no_fitness_termination = False

[DefaultGenome]
activation_default      = tanh
activation_mutate_rate  = 0.1
activation_options      = tanh clamped relu sigmoid

aggregation_default     = sum
aggregation_mutate_rate = 0.1
aggregation_options     = sum

feed_forward            = False
num_inputs              = 7
num_outputs             = 2
num_hidden              = 1

initial_connection      = full_direct
conn_add_prob           = 0.5
conn_delete_prob        = 0.2
node_add_prob           = 0.2
node_delete_prob        = 0.2

single_structural_mutation = False
structural_mutation_surer  = default

bias_init_mean = 0.0
bias_init_stdev = 1.0
bias_init_type = gaussian
bias_max_value = 10.0
bias_min_value = -10.0
bias_mutate_power = 0.5
bias_mutate_rate = 0.7
bias_replace_rate = 0.1

weight_init_mean = 0.0
weight_init_stdev = 1.0
weight_init_type = gaussian
weight_max_value = 10.0
weight_min_value = -10.0
weight_mutate_power = 0.5
weight_mutate_rate = 0.7
weight_replace_rate = 0.1

enabled_default = True
enabled_mutate_rate = 0.05
enabled_rate_to_false_add = 0.0
enabled_rate_to_true_add = 0.0
response_init_mean = 1.0
response_init_stdev = 0.0
response_init_type = gaussian
response_max_value = 10.0
response_min_value = -10.0
response_mutate_power = 0.0
response_mutate_rate = 0.0
response_replace_rate = 0.0

compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient   = 0.5

[DefaultSpeciesSet]
compatibility_threshold = 3.0

[DefaultStagnation]
species_fitness_func = max
max_stagnation       = 15
species_elitism      = 3

[DefaultReproduction]
elitism            = 3
survival_threshold = 0.3
min_species_size   = 2
"""


@dataclass
class NeatConfig:
    """NEAT configuration parameters."""

    pop_size: int = 150
    num_inputs: int = 7
    num_outputs: int = 2
    num_generations: int = 30
    fitness_threshold: float = 100000.0

    # Genome parameters
    activation_default: str = "tanh"
    activation_options: str = "tanh clamped relu sigmoid"
    feed_forward: bool = False

    # Structural mutation rates
    conn_add_prob: float = 0.5
    conn_delete_prob: float = 0.2
    node_add_prob: float = 0.2
    node_delete_prob: float = 0.2

    # Stagnation
    max_stagnation: int = 15
    species_elitism: int = 3

    # Reproduction
    elitism: int = 3
    survival_threshold: float = 0.3


def build_config_file(
    config: NeatConfig | None = None,
    filepath: str = "config-neat.txt",
) -> str:
    """Build and save NEAT configuration file.

    Args:
        config: NeatConfig instance (uses defaults if None)
        filepath: Path to save configuration file

    Returns:
        Path to saved configuration file
    """
    if config is None:
        config = NeatConfig()

    config_str = f"""[NEAT]
fitness_criterion     = max
fitness_threshold     = {config.fitness_threshold}
pop_size              = {config.pop_size}
reset_on_extinction   = False
no_fitness_termination = False

[DefaultGenome]
activation_default      = {config.activation_default}
activation_mutate_rate  = 0.1
activation_options      = {config.activation_options}

aggregation_default     = sum
aggregation_mutate_rate = 0.1
aggregation_options     = sum

feed_forward            = {str(config.feed_forward).lower()}
num_inputs              = {config.num_inputs}
num_outputs             = {config.num_outputs}
num_hidden              = 1

initial_connection      = full_direct
conn_add_prob           = {config.conn_add_prob}
conn_delete_prob        = {config.conn_delete_prob}
node_add_prob           = {config.node_add_prob}
node_delete_prob        = {config.node_delete_prob}

single_structural_mutation = False
structural_mutation_surer  = default

bias_init_mean = 0.0
bias_init_stdev = 1.0
bias_init_type = gaussian
bias_max_value = 10.0
bias_min_value = -10.0
bias_mutate_power = 0.5
bias_mutate_rate = 0.7
bias_replace_rate = 0.1

weight_init_mean = 0.0
weight_init_stdev = 1.0
weight_init_type = gaussian
weight_max_value = 10.0
weight_min_value = -10.0
weight_mutate_power = 0.5
weight_mutate_rate = 0.7
weight_replace_rate = 0.1

enabled_default = True
enabled_mutate_rate = 0.05
enabled_rate_to_false_add = 0.0
enabled_rate_to_true_add = 0.0
response_init_mean = 1.0
response_init_stdev = 0.0
response_init_type = gaussian
response_max_value = 10.0
response_min_value = -10.0
response_mutate_power = 0.0
response_mutate_rate = 0.0
response_replace_rate = 0.0

compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient   = 0.5

[DefaultSpeciesSet]
compatibility_threshold = 3.0

[DefaultStagnation]
species_fitness_func = max
max_stagnation       = {config.max_stagnation}
species_elitism      = {config.species_elitism}

[DefaultReproduction]
elitism            = {config.elitism}
survival_threshold = {config.survival_threshold}
min_species_size   = 2
"""

    with open(filepath, "w") as f:
        f.write(config_str)

    return filepath


def load_neat_config(filepath: str = "config-neat.txt") -> neat.Config:
    """Load NEAT configuration from file.

    Creates default config file if it doesn't exist.

    Args:
        filepath: Path to configuration file

    Returns:
        neat.Config instance ready for use
    """
    if not os.path.exists(filepath):
        build_config_file(filepath=filepath)

    return neat.Config(
        neat.DefaultGenome,
        neat.DefaultReproduction,
        neat.DefaultSpeciesSet,
        neat.DefaultStagnation,
        filepath,
    )


def create_default_config() -> neat.Config:
    """Create default NEAT configuration in memory.

    Returns:
        neat.Config with default parameters matching NEAT/main.py
    """
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(DEFAULT_CONFIG)
        temp_path = f.name

    try:
        config = neat.Config(
            neat.DefaultGenome,
            neat.DefaultReproduction,
            neat.DefaultSpeciesSet,
            neat.DefaultStagnation,
            temp_path,
        )
    finally:
        os.unlink(temp_path)

    return config


def get_config_summary(config: neat.Config) -> dict[str, Any]:
    """Get human-readable summary of NEAT configuration."""
    return {
        "pop_size": config.pop_size,
        "num_inputs": config.genome_config.num_inputs,
        "num_outputs": config.genome_config.num_outputs,
        "feed_forward": config.genome_config.feed_forward,
        "activation_default": config.genome_config.activation_default,
        "conn_add_prob": config.genome_config.conn_add_prob,
        "conn_delete_prob": config.genome_config.conn_delete_prob,
        "node_add_prob": config.genome_config.node_add_prob,
        "node_delete_prob": config.genome_config.node_delete_prob,
        "max_stagnation": config.stagnation_config.max_stagnation,
        "elitism": config.reproduction_config.elitism,
    }
