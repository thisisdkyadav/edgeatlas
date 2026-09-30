export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Edge-Token": sessionStorage.getItem("edgeatlas-token") || "",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const value = await response
      .json()
      .catch(() => ({ detail: "Connection failed." }));
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : JSON.stringify(value.detail),
    );
  }
  return response.json();
}
export async function download(format: string) {
  const response = await fetch("/api/export?format=" + format, {
    headers: {
      "X-Edge-Token": sessionStorage.getItem("edgeatlas-token") || "",
    },
  });
  if (!response.ok) throw new Error("Export failed.");
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "edgeatlas-memories." + format;
  a.click();
  URL.revokeObjectURL(url);
}
