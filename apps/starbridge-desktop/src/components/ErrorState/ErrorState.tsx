interface ErrorStateProps {
  title?: string;
  message: string;
  nextSteps?: string[];
}

export function ErrorState({ title = "这一步没有完成", message, nextSteps = [] }: ErrorStateProps) {
  return (
    <div className="error-state" role="alert">
      <strong>{title}</strong>
      <p>{message}</p>
      {nextSteps.length > 0 ? (
        <ul>{nextSteps.map((step) => <li key={step}>{step}</li>)}</ul>
      ) : null}
    </div>
  );
}
