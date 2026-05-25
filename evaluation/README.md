# Evaluation

Case study testing InstaMAL's expressiveness on a real adversary emulation scenario from the [CTID Adversary Emulation Library](https://github.com/center-for-threat-informed-defense/adversary_emulation_library).

An LLM (Claude Sonnet 4.6) was given a natural-language description of the scenario's system and asked to produce structural variability requirements, with no knowledge of InstaMAL. An InstaMAL specification was then written to satisfy those requirements, and a rubric check script verifies them across a population of generated instances.

The reference [coreLang](https://github.com/mal-lang/coreLang) model instance for the scenario is in [sandorstormen/emulation-plan-scenarios](https://github.com/sandorstormen/emulation-plan-scenarios/blob/main/scenarios/menuPass_scenario1.yml). Details are in Chapters 5–7 of the thesis.

## Structure

```
evaluation/
├── coreLang-1.0.0.mar          # coreLang DSL used for the evaluation
├── prompt.txt                  # LLM prompt template for requirement generation
└── menuPass_scenario1/         # The evaluated case study
    ├── system_description.txt  # Domain description supplied to the LLM
    ├── llm_output.txt          # LLM-generated requirements and rubric
    ├── specification.spec      # InstaMAL specification
    ├── rubric_checks.py        # Automated rubric checks (R1–R9)
    └── generated/              # Output directory for generated instances
```

## Running the checks

From the project root:

```bash
# Generate 100 instances and run all checks
python evaluation/menuPass_scenario1/rubric_checks.py

# Use 5000 instances (as in the thesis)
python evaluation/menuPass_scenario1/rubric_checks.py -n 5000

# Regenerate even if instances already exist
python evaluation/menuPass_scenario1/rubric_checks.py -n 5000 --regen
```

The script generates coreLang model instances from `specification.spec`, writes them to `generated/`, and runs nine checks against the population. Each check is either mandatory (must hold in every instance) or distributional (must hold across the population within specified thresholds).
