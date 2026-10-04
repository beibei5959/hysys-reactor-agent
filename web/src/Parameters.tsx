import { useEffect, useState } from "react";
import { ArrowRight, Plus, Trash2 } from "lucide-react";
import type { ReactionInfo, SelectionPreview, SimulationInputs } from "./types";
import { api } from "./api";
import ReactionEditor, {
  equationDraft,
  equationValues,
} from "./ReactionEditor";

type Props = {
  info: ReactionInfo;
  inputs: SimulationInputs;
  reactor?: string | null;
  busy: boolean;
  onRun: (info: ReactionInfo, inputs: SimulationInputs) => Promise<void>;
};
function number(value: string) {
  return value.trim() === "" ? null : Number(value);
}

export default function Parameters({
  info,
  inputs,
  reactor,
  busy,
  onRun,
}: Props) {
  const [temperature, setTemperature] = useState(
    String(info.temperature ?? ""),
  );
  const [pressure, setPressure] = useState(String(info.pressure ?? ""));
  const [conversion, setConversion] = useState(
    info.conversion == null ? "" : String(info.conversion * 100),
  );
  const [flow, setFlow] = useState(String(inputs.feed_flow_kmol_h ?? ""));
  const [components, setComponents] = useState(
    (inputs.components ?? []).join(", "),
  );
  const [reactants, setReactants] = useState((info.reactants ?? []).join(", "));
  const [products, setProducts] = useState((info.products ?? []).join(", "));
  const conditions = [
    ["conversion_known", "是否明确给定转化率"],
    ["reversible", "是否为可逆反应"],
    ["equilibrium_controlled", "是否受平衡控制"],
    ["multiple_reactions", "是否存在多个反应"],
    ["products_known", "产物是否明确"],
    ["reaction_path_known", "反应路径是否明确"],
  ] as const;
  const [flags, setFlags] = useState(
    Object.fromEntries(
      conditions.map(([name]) => [name, info[name] ?? null]),
    ) as Record<(typeof conditions)[number][0], boolean | null>,
  );
  const [property, setProperty] = useState(inputs.property_package ?? "");
  const [basis, setBasis] = useState(inputs.conversion_basis ?? "");
  const [method, setMethod] = useState(inputs.equilibrium_method ?? "");
  const [composition, setComposition] = useState(
    Object.entries(inputs.feed_composition ?? {}).map(([name, value]) => ({
      name,
      value: String(value),
    })),
  );
  const [reactions, setReactions] = useState(() =>
    equationDraft(inputs.reactions ?? []),
  );
  const [preview, setPreview] = useState<SelectionPreview>({
    selected_reactor: reactor ?? null,
    selection_reason: "",
    confidence: 0,
  });
  const [resolvedSignature, setResolvedSignature] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [previewAttempt, setPreviewAttempt] = useState(0);
  const selectionSignature = JSON.stringify({
    ...flags,
    conversion:
      flags.conversion_known && conversion !== ""
        ? Number(conversion) / 100
        : null,
  });
  const previewReady =
    selectionSignature === resolvedSignature && !previewError;
  const selectedReactor = preview.selected_reactor;
  useEffect(() => {
    let live = true;
    setPreviewError("");
    const timer = window.setTimeout(() => {
      api
        .preview(JSON.parse(selectionSignature))
        .then((result) => {
          if (live) {
            setPreview(result);
            setResolvedSignature(selectionSignature);
          }
        })
        .catch((error) => {
          if (live) setPreviewError((error as Error).message);
        });
    }, 200);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [selectionSignature, previewAttempt]);
  const [error, setError] = useState("");
  const list = (value: string) =>
    value
      .split(/[,，、\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    if (!previewReady) return;
    try {
      const entries = composition.filter(
        (row) => row.name.trim() || row.value.trim(),
      );
      if (entries.some((row) => !row.name.trim() || !row.value.trim()))
        throw new Error("请完整填写每一行进料组分和摩尔分率。");
      if (
        new Set(entries.map((row) => row.name.trim())).size !== entries.length
      )
        throw new Error("进料组分不能重复。");
      const parsed =
        selectedReactor === "Gibbs" ? [] : equationValues(reactions);
      const feed = Object.fromEntries(
        entries.map((row) => [row.name.trim(), Number(row.value)]),
      );
      if (
        Object.values(feed).some((n) => !Number.isFinite(n) || n < 0 || n > 1)
      )
        throw new Error("摩尔分率必须为0到1。");
      if (
        entries.length &&
        Math.abs(Object.values(feed).reduce((a, b) => a + b, 0) - 1) > 0.000001
      )
        throw new Error("进料摩尔分率之和必须为1。");
      await onRun(
        {
          ...info,
          ...flags,
          temperature: number(temperature),
          pressure: number(pressure),
          reactants: list(reactants),
          products: list(products),
          conversion:
            flags.conversion_known && conversion !== ""
              ? Number(conversion) / 100
              : null,
        },
        {
          ...inputs,
          components: list(components),
          property_package: property,
          feed_flow_kmol_h: number(flow),
          feed_composition: feed,
          reactions: parsed,
          conversion_basis:
            selectedReactor === "Conversion" ? basis || null : null,
          equilibrium_method:
            selectedReactor === "Equilibrium" ? method || null : null,
        },
      );
    } catch (error) {
      setError((error as Error).message);
    }
  }
  return (
    <form className="parameters" onSubmit={submit}>
      <div className="selection-preview" role="status">
        {previewError ? (
          <>
            {previewError}{" "}
            <button
              type="button"
              className="text-button"
              onClick={() => setPreviewAttempt((n) => n + 1)}
            >
              重试选型检查
            </button>
          </>
        ) : !previewReady ? (
          "正在根据当前条件检查选型…"
        ) : (
          <>
            <strong>
              当前参数预选型：
              {(
                {
                  Conversion: "转化反应器",
                  Equilibrium: "平衡反应器",
                  Gibbs: "吉布斯反应器",
                } as Record<string, string>
              )[selectedReactor ?? ""] ?? "待补充选型依据"}
            </strong>
            <span>{preview.selection_reason}</span>
          </>
        )}
      </div>
      <div className="section-label">
        <span>01</span> 反应条件
      </div>
      <div className="field-grid">
        <label>
          温度 <span className="unit">K</span>
          <input
            type="number"
            step="any"
            min="0.000001"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
            placeholder="待补充"
          />
        </label>
        <label>
          绝对压力 <span className="unit">kPa</span>
          <input
            type="number"
            step="any"
            min="0.000001"
            value={pressure}
            onChange={(e) => setPressure(e.target.value)}
            placeholder="待补充"
          />
        </label>
        {(selectedReactor === "Conversion" || flags.conversion_known) && (
          <label>
            转化率 <span className="unit">%</span>
            <input
              type="number"
              step="any"
              min="0"
              max="100"
              value={conversion}
              onChange={(e) => setConversion(e.target.value)}
              placeholder="待补充"
            />
          </label>
        )}
        <label>
          反应物
          <input
            value={reactants}
            onChange={(e) => setReactants(e.target.value)}
            placeholder="例如 CH4, H2O"
          />
        </label>
        <label>
          已知产物
          <input
            value={products}
            onChange={(e) => setProducts(e.target.value)}
            placeholder="产物未知时留空"
          />
        </label>
      </div>
      <details className="condition-details">
        <summary>核对反应特征与选型条件</summary>
        <div className="field-grid">
          {conditions.map(([name, label]) => (
            <label key={name}>
              {label}
              <select
                value={flags[name] === null ? "" : String(flags[name])}
                onChange={(e) =>
                  setFlags({
                    ...flags,
                    [name]:
                      e.target.value === "" ? null : e.target.value === "true",
                  })
                }
              >
                <option value="">尚不确定</option>
                <option value="true">是</option>
                <option value="false">否</option>
              </select>
            </label>
          ))}
        </div>
        <p className="muted">
          修改条件后会立即按后端工程规则更新预选型及专用参数；确认运行时再次校验。
        </p>
      </details>
      <div className="section-label">
        <span>02</span> 进料与物性
      </div>
      <div className="field-grid">
        <label className="span-two">
          候选组分 <span className="unit">逗号分隔</span>
          <input
            value={components}
            onChange={(e) => setComponents(e.target.value)}
            placeholder="填写全部候选组分"
          />
        </label>
        <label>
          进料总摩尔流量 <span className="unit">kmol/h</span>
          <input
            type="number"
            min="0.000001"
            step="any"
            value={flow}
            onChange={(e) => setFlow(e.target.value)}
            placeholder="待补充"
          />
        </label>
        <label>
          物性包
          <input
            value={property}
            onChange={(e) => setProperty(e.target.value)}
            placeholder="请填写经确认的物性方法"
          />
        </label>
      </div>
      <div className="composition-table">
        <div className="composition-heading">
          <span>进料组分</span>
          <span>摩尔分率（0—1）</span>
          <span />
        </div>
        {composition.map((row, index) => (
          <div className="composition-row" key={index}>
            <input
              aria-label={`进料组分 ${index + 1}`}
              value={row.name}
              onChange={(e) =>
                setComposition(
                  composition.map((r, i) =>
                    i === index ? { ...r, name: e.target.value } : r,
                  ),
                )
              }
              placeholder="组分名称"
            />
            <input
              aria-label={`摩尔分率 ${index + 1}`}
              type="number"
              step="any"
              min="0"
              max="1"
              value={row.value}
              onChange={(e) =>
                setComposition(
                  composition.map((r, i) =>
                    i === index ? { ...r, value: e.target.value } : r,
                  ),
                )
              }
              placeholder="0.00"
            />
            <button
              type="button"
              className="icon-button"
              aria-label={`删除组分 ${index + 1}`}
              onClick={() =>
                setComposition(composition.filter((_, i) => i !== index))
              }
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
        <button
          className="text-button"
          type="button"
          onClick={() =>
            setComposition([...composition, { name: "", value: "" }])
          }
        >
          <Plus size={15} /> 添加进料组分
        </button>
      </div>
      {selectedReactor !== "Gibbs" && (
        <>
          <div className="section-label">
            <span>03</span> 反应器专用参数
          </div>
          <div className="field-grid">
            {selectedReactor === "Conversion" && (
              <label className="span-two">
                转化基准组分
                <input
                  value={basis}
                  onChange={(e) => setBasis(e.target.value)}
                  placeholder="例如 C7H8"
                />
              </label>
            )}
            {selectedReactor === "Equilibrium" && (
              <label className="span-two">
                平衡数据来源 / 方法
                <input
                  value={method}
                  onChange={(e) => setMethod(e.target.value)}
                  placeholder="填写经确认的方法"
                />
              </label>
            )}
            <div className="span-two">
              <ReactionEditor value={reactions} onChange={setReactions} />
            </div>
          </div>
        </>
      )}
      {error && (
        <div role="alert" className="error-banner">
          {error}
        </div>
      )}
      <div className="parameter-footer">
        <span>确认后重新校验并运行 Mock 流程；保留原任务记录。</span>
        <button className="primary" disabled={busy || !previewReady}>
          {busy ? (
            <>
              <span className="spinner" /> 提交中
            </>
          ) : (
            <>
              确认参数并运行 <ArrowRight size={16} />
            </>
          )}
        </button>
      </div>
    </form>
  );
}
