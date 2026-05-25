"""Parity configuration tests for NEAT config builder."""

import pytest

from stonks_trading.domains.trading.neat.config_builder import (
    DEFAULT_CONFIG,
    create_default_config,
)


class TestConfigParity:
    """Test NEAT configuration parity with NEAT/main.py lines 341-421."""

    def test_default_config_matches_original(self) -> None:
        """Verify default config matches NEAT/main.py make_config()."""
        config = create_default_config()

        # NEAT section
        assert config.fitness_criterion == "max"
        assert config.fitness_threshold == 100000
        assert config.pop_size == 150
        assert config.reset_on_extinction is False

    def test_genome_config_structure(self) -> None:
        """Verify genome configuration structure."""
        config = create_default_config()

        # Genome parameters
        assert config.genome_config.num_inputs == 7  # 7 inputs: [is_invested, unrealized_pnl, 5 features]
        assert config.genome_config.num_outputs == 2  # 2 outputs: [buy, sell]
        assert config.genome_config.num_hidden == 1
        assert config.genome_config.feed_forward is False  # Recurrent network

    def test_activation_functions(self) -> None:
        """Verify activation function options."""
        config = create_default_config()

        expected_activations = ["tanh", "clamped", "relu", "sigmoid"]
        assert list(config.genome_config.activation_options) == expected_activations
        assert config.genome_config.activation_default == "tanh"

    def test_structural_mutation_rates(self) -> None:
        """Verify structural mutation rates match NEAT/main.py."""
        config = create_default_config()

        # These should match the values in NEAT/main.py make_config()
        assert config.genome_config.conn_add_prob == 0.5
        assert config.genome_config.conn_delete_prob == 0.2
        assert config.genome_config.node_add_prob == 0.2
        assert config.genome_config.node_delete_prob == 0.2

    def test_weight_mutation_rates(self) -> None:
        """Verify weight mutation configuration."""
        config = create_default_config()

        assert config.genome_config.weight_mutate_rate == 0.7
        assert config.genome_config.weight_mutate_power == 0.5
        assert config.genome_config.weight_replace_rate == 0.1
        assert config.genome_config.weight_max_value == 10.0
        assert config.genome_config.weight_min_value == -10.0

    def test_species_configuration(self) -> None:
        """Verify species configuration matches original."""
        config = create_default_config()

        assert config.species_set_config.compatibility_threshold == 3.0

    def test_stagnation_configuration(self) -> None:
        """Verify stagnation configuration."""
        config = create_default_config()

        assert config.stagnation_config.max_stagnation == 15
        assert config.stagnation_config.species_elitism == 3
        assert config.stagnation_config.species_fitness_func == "max"

    def test_reproduction_configuration(self) -> None:
        """Verify reproduction configuration."""
        config = create_default_config()

        assert config.reproduction_config.elitism == 3
        assert config.reproduction_config.survival_threshold == 0.3
        assert config.reproduction_config.min_species_size == 2

    def test_default_config_string_matches(self) -> None:
        """Verify DEFAULT_CONFIG string contains expected values."""
        # Check that the config string contains key values from NEAT/main.py
        assert "fitness_criterion     = max" in DEFAULT_CONFIG
        assert "pop_size              = 150" in DEFAULT_CONFIG
        assert "num_inputs              = 7" in DEFAULT_CONFIG
        assert "num_outputs             = 2" in DEFAULT_CONFIG
        assert "feed_forward            = False" in DEFAULT_CONFIG
        assert "max_stagnation       = 15" in DEFAULT_CONFIG
        assert "species_elitism      = 3" in DEFAULT_CONFIG
