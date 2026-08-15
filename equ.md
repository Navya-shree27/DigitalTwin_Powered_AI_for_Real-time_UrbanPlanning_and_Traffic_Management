# Validated Mathematical Metrics for Data-Driven Renovation Plans

**Scope:** Signal timing, lane configuration, and zoning improvements.

This document contains mathematical equations published or used by other researchers. It distinguishes between established metrics, analytical approximations, and reinforcement-learning reward functions.

## 1. Intersection Delay

A peer-reviewed traffic-signal-control paper defines intersection delay as a flow-weighted delay across approaches:

\[
d_I' =
\frac{\sum_{i=1}^{m} td_i}
{\sum_{i=1}^{m} v_i n_i}
\]

Where:

- \(td_i\) = total delay for movement or approach \(i\).
- \(v_i\) = flow rate for movement \(i\).
- \(n_i\) = number of lanes serving movement \(i\).
- \(m\) = number of movements or approaches.

This is based on the Highway Capacity Manual delay concept and was used as a performance measure in reinforcement-learning traffic-signal research. [web:60]

### Python implementation

```python
def weighted_intersection_delay(total_delay, flow_rate, lane_count):
    """
    total_delay: list or array of td_i values
    flow_rate: list or array of v_i values
    lane_count: list or array of n_i values

    Returns delay in time units per vehicle-lane unit.
    """
    denominator = sum(v * n for v, n in zip(flow_rate, lane_count))

    if denominator <= 0:
        return 0.0

    return sum(total_delay) / denominator
```

This is a published mathematical metric, not an arbitrary project-specific formula.

## 2. Delay Entropy and Fairness

The same research defines delay entropy as:

\[
H_t = -\sum_{i=1}^{m} p_i \ln(p_i)
\]

where:

\[
p_i =
\frac{td_i}
{\sum_{j=1}^{m} td_j}
\]

Here, \(p_i\) is the proportion of total intersection delay experienced by movement \(i\). [web:60]

### Python implementation

```python
import math


def delay_entropy(total_delay):
    """
    total_delay: delay associated with each movement or approach.

    Higher entropy generally means delay is distributed across
    more movements instead of concentrated in one movement.
    """
    total = sum(total_delay)

    if total <= 0:
        return 0.0

    probabilities = [
        delay / total
        for delay in total_delay
        if delay > 0
    ]

    return -sum(p * math.log(p) for p in probabilities)
```

Use entropy together with total delay. Entropy alone should not be optimized blindly: a system could increase delay for everyone and produce a more even distribution.

## 3. Published Queue-Reduction Reward

A traffic-signal paper defines queue length for each approach as the maximum queue on any lane in that approach:

\[
Q_{j,t} =
\max_{l \in \mathcal{L}_j} q_{l,t}
\]

It then defines the reward:

\[
r_t =
\alpha_{\text{abs}}
\left(
-\frac{\sum_{j=1}^{N}Q_{j,t}}
{N Q_{\text{norm}}}
\right)
+
\alpha_{\text{red}}
\left(
\frac{\sum_{j=1}^{N}(Q_{j,t-1}-Q_{j,t})}
{N Q_{\text{norm}}}
\right)
\]

The authors report:

\[
\alpha_{\text{abs}} = 0.4,
\qquad
\alpha_{\text{red}} = 0.6
\]

The formula penalizes the current queue while rewarding queue reduction. [web:55]

### Python implementation

```python
def approach_queue_length(lane_queue_lengths):
    """
    lane_queue_lengths:
        Example: [12, 8, 10] for the lanes of one approach.

    The published formulation uses the maximum lane queue.
    """
    return max(lane_queue_lengths, default=0)


def queue_reduction_reward(
    previous_approach_queues,
    current_approach_queues,
    q_norm,
    alpha_abs=0.4,
    alpha_red=0.6
):
    """
    Each list contains one queue value per approach.

    Queue values must already be computed as:
        Q_j,t = max(queue on lanes of approach j)
    """
    n = len(current_approach_queues)

    if n == 0 or q_norm <= 0:
        return 0.0

    current_total = sum(current_approach_queues)
    reduction_total = sum(
        previous - current
        for previous, current in zip(
            previous_approach_queues,
            current_approach_queues
        )
    )

    absolute_penalty = -current_total / (n * q_norm)
    reduction_reward = reduction_total / (n * q_norm)

    return (
        alpha_abs * absolute_penalty
        + alpha_red * reduction_reward
    )
```

## 4. Webster's Signal-Timing Equation

Webster's *Traffic Signal Settings* is a foundational traffic-engineering work. It presents equations for average delay, optimum cycle length, and signalized-intersection capacity. [web:63]

A commonly used Webster optimum cycle-length equation is:

\[
C_0 =
\frac{1.5L + 5}
{1-Y}
\]

Where:

- \(C_0\) = estimated optimum cycle length in seconds.
- \(L\) = total lost time per cycle.
- \(Y\) = sum of critical flow ratios.

The critical flow ratio is:

\[
Y = \sum_i \frac{q_i}{s_i}
\]

Where:

- \(q_i\) = demand flow for critical movement \(i\).
- \(s_i\) = saturation flow for that movement.

### Python implementation

```python
def webster_cycle_length(lost_time, flow_rates, saturation_flows):
    """
    Classical Webster optimum cycle-length equation.

    flow_rates and saturation_flows must use matching units,
    such as vehicles/hour for both.
    """
    critical_flow_ratios = [
        q / s
        for q, s in zip(flow_rates, saturation_flows)
        if s > 0
    ]

    Y = sum(critical_flow_ratios)

    if Y >= 1:
        # Demand reaches or exceeds theoretical capacity.
        return float("inf")

    return (1.5 * lost_time + 5) / (1 - Y)
```

This equation is an analytical approximation. It should be used as a conventional baseline against which AI-generated signal plans are compared, not as a guarantee of real-world optimality. Webster's delay formula has also been compared with Highway Capacity Manual, Australian, and Canadian formulations in later research. [web:66]

## 5. Land-Use Mix Entropy

For zoning and land-use renovation, the normalized Shannon entropy index is widely used in quantitative urban studies:

\[
ENT =
-\frac{\sum_{i=1}^{k}P_i\ln(P_i)}
{\ln(k)}
\]

Where:

- \(P_i\) = proportion of land-use type \(i\) in the zone.
- \(k\) = number of land-use types represented in the zone.

The value ranges from 0 to 1:

- \(ENT=0\): single-use development.
- \(ENT=1\): equal distribution across all represented land-use categories.

This equation is reported in urban-planning research and reviews of land-use-mix indices. [web:52][web:67]

### Python implementation

```python
import math


def land_use_entropy(area_by_type):
    """
    area_by_type:
        Example:
        {
            "residential": 4000,
            "commercial": 2000,
            "public": 1000
        }

    Returns normalized entropy between 0 and 1.
    """
    positive_areas = [
        area
        for area in area_by_type.values()
        if area > 0
    ]

    if len(positive_areas) <= 1:
        return 0.0

    total_area = sum(positive_areas)
    proportions = [
        area / total_area
        for area in positive_areas
    ]

    raw_entropy = -sum(
        p * math.log(p)
        for p in proportions
    )

    return raw_entropy / math.log(len(proportions))
```

One important caveat: entropy measures composition, not whether land uses are well-located, accessible, or compatible. Research has identified limitations in entropy-based land-use-mix indices, so entropy should not be your only zoning metric. [web:69]

## 6. Metrics to Use in Your Renovation Engine

| Objective | Primary published equation | Decision produced |
|---|---|---|
| Signal timing | Weighted intersection delay | Whether timing reduces delay fairly across movements |
| Signal timing | Queue-reduction reward | RL controller objective |
| Signal timing baseline | Webster cycle length | Conventional benchmark plan |
| Lane changes | Delay, queue, throughput, and flow ratios | Whether lane-direction changes improve network performance |
| Zoning | Normalized Shannon entropy | Whether land-use mix becomes more balanced |
| Zoning validation | Accessibility and travel-time analysis | Whether the proposed zoning is useful to residents |

## 7. Before-and-After Evaluation Equation

For each metric, compare the baseline simulation with the proposed renovation:

\[
\Delta M =
\frac{M_{\text{baseline}} - M_{\text{proposed}}}
{M_{\text{baseline}}}
\times 100
\]

Use this form for metrics that should decrease, such as:

- Average delay.
- Queue length.
- Travel time.
- Number of stops.
- Emissions.

For metrics that should increase, such as throughput or accessibility, use:

\[
\Delta M_{\text{increase}} =
\frac{M_{\text{proposed}} - M_{\text{baseline}}}
{M_{\text{baseline}}}
\times 100
\]

### Python implementation

```python
def percent_improvement(baseline, proposed, direction="decrease"):
    """
    direction='decrease' for delay, queue, travel time, etc.
    direction='increase' for throughput, accessibility, etc.
    """
    if baseline == 0:
        return 0.0

    if direction == "decrease":
        return ((baseline - proposed) / baseline) * 100

    if direction == "increase":
        return ((proposed - baseline) / baseline) * 100

    raise ValueError("direction must be 'decrease' or 'increase'")
```

## 8. Important Scientific Limitations

The equations above are valid published metrics, but they do not all have the same scientific status:

- Webster's equation is an analytical approximation.
- Queue and delay metrics are established traffic-performance measures.
- The queue-reduction equation is a published reinforcement-learning reward function, but its effectiveness depends on state representation, action space, demand data, and simulator calibration.
- Shannon entropy is an established land-use-mix measure, but it does not measure accessibility or land-use compatibility by itself.
- Lane reconfiguration does not have one universally accepted single equation. Research generally evaluates lane plans using network-wide delay, queue, throughput, travel time, and capacity outcomes. [web:31][web:39]

## 9. Recommended Acceptance Rule

A proposed renovation should be accepted only when it improves the intended metric without creating unacceptable regressions:

```python
def renovation_is_acceptable(
    baseline_delay,
    proposed_delay,
    baseline_queue,
    proposed_queue,
    baseline_throughput,
    proposed_throughput,
    minimum_delay_reduction=0.05,
    maximum_queue_increase=0.05,
    minimum_throughput_change=-0.02
):
    """
    Example conservative acceptance rule.

    Values such as 0.05 and 0.02 are project policy thresholds,
    not universal scientific constants. Tune them with domain experts.
    """
    delay_change = (baseline_delay - proposed_delay) / baseline_delay
    queue_change = (proposed_queue - baseline_queue) / baseline_queue
    throughput_change = (
        (proposed_throughput - baseline_throughput)
        / baseline_throughput
    )

    return (
        delay_change >= minimum_delay_reduction
        and queue_change <= maximum_queue_increase
        and throughput_change >= minimum_throughput_change
    )
```

The acceptance thresholds in this final example are policy choices. They are not claimed to be published universal constants. The published equations are the metric definitions used to calculate and compare the scenarios.

## Sources

- Effects analysis of reward functions for reinforcement-learning traffic signal control. [web:60]
- Advances in reinforcement learning for traffic signal control: a review of recent progress. [web:45]
- Reinforcement Learning Based Traffic Signal Design to Minimize Queue Length. [web:55]
- Webster, F. V., *Traffic Signal Settings*. [web:63]
- The Highway Capacity Manual delay formula and related analytical comparisons. [web:66]
- *New Methods for Assessing Land Use*. [web:52]
- *The Hidden Characteristics of Land-Use Mix Indices*. [web:67][web:69]
- Real-Time Lane Configuration with Coordinated Reinforcement Learning. [web:39]
- Real-time Road Network Optimization with Coordinated Reinforcement Learning. [web:31]