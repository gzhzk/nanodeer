"""Harbor integration for running NanoDeer as an installed agent.

Import ``nanodeer.integrations.harbor.agent:NanoDeerHarborAgent`` from Harbor.
The package init avoids importing Harbor unless that explicit adapter path is
used, keeping the main NanoDeer runtime free of Harbor as a dependency.
"""

