# ADR-0002: Select the A-source Vue application as the initial canonical frontend

The B source directory currently contains plans and governance documents but no runnable frontend. The A source contains a Vue/Vite customer interface. It is imported once into `frontend/` as the initial B-owned frontend baseline. No duplicate production frontend is retained; later B work replaces or evolves it through the normal contract process.
