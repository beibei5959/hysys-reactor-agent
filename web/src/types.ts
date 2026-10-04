export type User = { id: string; username: string; role: "admin" | "user" };
export type ReactionInfo = {
  reaction_name?: string | null;
  reactants?: string[];
  products?: string[];
  temperature?: number | null;
  pressure?: number | null;
  conversion?: number | null;
  reversible?: boolean | null;
  multiple_reactions?: boolean | null;
  conversion_known?: boolean | null;
  equilibrium_controlled?: boolean | null;
  products_known?: boolean | null;
  reaction_path_known?: boolean | null;
};
export type SimulationInputs = {
  components?: string[];
  property_package?: string;
  feed_composition?: Record<string, number>;
  feed_flow_kmol_h?: number | null;
  reactions?: Record<string, number>[];
  conversion_basis?: string | null;
  equilibrium_method?: string | null;
};
export type ModelTrace = {
  phase: string;
  provider: string;
  model: string;
  status: string;
  reason?: string;
  duration_ms?: number;
};
export type AgentState = {
  user_query: string;
  reaction_info?: ReactionInfo | null;
  simulation_inputs?: SimulationInputs;
  selected_reactor?: string | null;
  selection_reason?: string;
  missing_parameters?: string[];
  validation_passed?: boolean;
  simulation_status?: string;
  final_answer?: string;
  simulation_results?: {
    source?: string;
    converged?: boolean | null;
    engineering_results?: unknown;
  };
  llm_trace?: ModelTrace[];
  error?: string | null;
  explanation_status?: string;
  cleanup_status?: string;
};
export type Task = {
  id: string;
  title: string;
  status: string;
  stage: string | null;
  created: number;
  updated: number;
  owner: string;
  state: AgentState;
  parent_id?: string | null;
  root_id: string;
  revision: number;
};
export type TaskHistory = {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
};
export type SelectionPreview = {
  selected_reactor: string | null;
  selection_reason: string;
  confidence: number;
};
export type Example = {
  id: string;
  title: string;
  subtitle: string;
  user_query: string;
  reaction_info: ReactionInfo;
  simulation_inputs: SimulationInputs;
};
