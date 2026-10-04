import { Plus, Trash2 } from "lucide-react";

export type Term = {
  name: string;
  side: "reactant" | "product";
  coefficient: string;
};
export type Equation = Term[];
export function equationDraft(reactions: Record<string, number>[]): Equation[] {
  return reactions.map((reaction) =>
    Object.entries(reaction).map(([name, amount]) => ({
      name,
      side: amount < 0 ? "reactant" : "product",
      coefficient: String(Math.abs(amount)),
    })),
  );
}
export function equationValues(
  equations: Equation[],
): Record<string, number>[] {
  return equations.map((terms, index) => {
    if (terms.length < 2)
      throw new Error(`反应 ${index + 1} 至少需要一项反应物和一项产物。`);
    const values: Record<string, number> = Object.create(null);
    for (const term of terms) {
      const name = term.name.trim();
      const coefficient = Number(term.coefficient);
      if (
        !name ||
        !term.coefficient.trim() ||
        !Number.isFinite(coefficient) ||
        coefficient <= 0
      )
        throw new Error(`请完整填写反应 ${index + 1} 的组分和正数系数。`);
      if (Object.hasOwn(values, name))
        throw new Error(
          `反应 ${index + 1} 中的组分「${name}」重复，请合并系数。`,
        );
      values[name] = coefficient * (term.side === "reactant" ? -1 : 1);
    }
    if (
      !terms.some((term) => term.side === "reactant") ||
      !terms.some((term) => term.side === "product")
    )
      throw new Error(`反应 ${index + 1} 需要同时包含反应物和产物。`);
    return values;
  });
}

export default function ReactionEditor({
  value,
  onChange,
}: {
  value: Equation[];
  onChange: (value: Equation[]) => void;
}) {
  function change(index: number, terms: Equation) {
    onChange(value.map((equation, i) => (i === index ? terms : equation)));
  }
  return (
    <div className="reaction-editor">
      <h3>反应计量方程</h3>
      <p className="muted">
        分别填写反应物、产物及正数计量系数；组分名称应与候选组分一致。
      </p>
      {value.map((terms, index) => (
        <fieldset key={index}>
          <legend>反应 {index + 1}</legend>
          {terms.map((term, termIndex) => (
            <div className="reaction-term" key={termIndex}>
              <select
                aria-label={`反应 ${index + 1} 第 ${termIndex + 1} 项方向`}
                value={term.side}
                onChange={(e) =>
                  change(
                    index,
                    terms.map((t, j) =>
                      j === termIndex
                        ? { ...t, side: e.target.value as Term["side"] }
                        : t,
                    ),
                  )
                }
              >
                <option value="reactant">反应物</option>
                <option value="product">产物</option>
              </select>
              <input
                aria-label={`反应 ${index + 1} 第 ${termIndex + 1} 项组分`}
                placeholder="组分名称"
                value={term.name}
                onChange={(e) =>
                  change(
                    index,
                    terms.map((t, j) =>
                      j === termIndex ? { ...t, name: e.target.value } : t,
                    ),
                  )
                }
              />
              <input
                aria-label={`反应 ${index + 1} 第 ${termIndex + 1} 项系数`}
                type="number"
                min="0.000001"
                step="any"
                placeholder="系数"
                value={term.coefficient}
                onChange={(e) =>
                  change(
                    index,
                    terms.map((t, j) =>
                      j === termIndex
                        ? { ...t, coefficient: e.target.value }
                        : t,
                    ),
                  )
                }
              />
              <button
                type="button"
                className="icon-button"
                aria-label={`删除反应 ${index + 1} 第 ${termIndex + 1} 项`}
                onClick={() =>
                  change(
                    index,
                    terms.filter((_, j) => j !== termIndex),
                  )
                }
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          <div className="equation-actions">
            <button
              type="button"
              className="text-button"
              onClick={() =>
                change(index, [
                  ...terms,
                  { name: "", side: "product", coefficient: "1" },
                ])
              }
            >
              <Plus size={14} />
              添加组分项
            </button>
            <button
              type="button"
              className="text-button"
              onClick={() => onChange(value.filter((_, i) => i !== index))}
            >
              删除此反应
            </button>
          </div>
        </fieldset>
      ))}
      <button
        type="button"
        className="text-button"
        onClick={() =>
          onChange([
            ...value,
            [
              { name: "", side: "reactant", coefficient: "1" },
              { name: "", side: "product", coefficient: "1" },
            ],
          ])
        }
      >
        <Plus size={15} />
        添加反应方程
      </button>
    </div>
  );
}
