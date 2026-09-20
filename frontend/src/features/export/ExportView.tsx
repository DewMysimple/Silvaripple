import { PageIntro } from "../../ui/layout";
import {
  ExportAdvanced,
  ExportDestination,
  ExportFormats,
} from "./ExportOptions";
import { ExportOutcome, ExportReview } from "./ExportReview";
import { ExportScope } from "./ExportScope";
import { useExportWorkbench } from "./useExportWorkbench";
import "./export.css";

export function ExportView() {
  const model = useExportWorkbench();
  if (!model.draft)
    return (
      <div className="page export-page">
        <p role="status">正在载入导出设置…</p>
      </div>
    );
  return (
    <div className="page export-page">
      <PageIntro
        title="整理好范围，安心保存"
        description="选择聊天内容与归档方式，导出一份可以长期保存的本地副本。"
        eyebrow="聊天归档"
      />
      <ExportOutcome model={model} />
      <div className="export-workspace">
        <div className="export-configuration">
          <fieldset
            className="export-config-fields"
            disabled={model.running || model.starting}
          >
            <ExportScope
              rows={model.selectedRows}
              draft={model.draft}
              onChange={model.updateDraft}
              onRemove={model.removeConversation}
              onClear={model.clearSelected}
              onAdd={model.addConversations}
            />
            <ExportFormats draft={model.draft} onChange={model.updateDraft} />
            <ExportDestination
              draft={model.draft}
              layout={model.settings?.export_folder_layout}
              onChoose={() => void model.chooseOutput()}
              onOpen={(path) => void model.openFolder(path)}
            />
            <ExportAdvanced draft={model.draft} onChange={model.updateDraft} />
          </fieldset>
        </div>
        <aside className="export-review-column">
          <ExportReview model={model} />
        </aside>
      </div>
    </div>
  );
}
