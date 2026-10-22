import { Icon } from "./Icon";

export function PreparingBadge({ percent }: { percent: number }) {
  return (
    <span className="or-badge or-badge--preparing">
      <Icon name="spinner" spin />
      Preparing… {percent}%
    </span>
  );
}

export function ReadyBadge() {
  return (
    <span className="or-badge or-badge--ready">
      <Icon name="check" />
      Ready
    </span>
  );
}

export function FailedBadge() {
  return (
    <span className="or-badge or-badge--failed">
      <Icon name="alert" />
      Failed
    </span>
  );
}

export function ProgressBar({ percent }: { percent: number }) {
  return (
    <div className="or-progress">
      <div className="or-progress__track" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
        <div className="or-progress__fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="or-progress__value">{percent}%</span>
    </div>
  );
}

export function ErrorLine({ children }: { children: React.ReactNode }) {
  return (
    <span className="or-error" role="alert">
      <Icon name="alert" />
      {children}
    </span>
  );
}
