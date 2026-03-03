import { createHeadersAsync, API_BASE_URL, handleResponse } from "./apiUtils";

export interface AIChatResponse {
  message: string;
}

export async function sendChatMessage(question: string): Promise<AIChatResponse> {
  const headers = await createHeadersAsync();
  const response = await fetch(`${API_BASE_URL}/api/ai/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ question: question.trim() }),
  });
  return handleResponse<AIChatResponse>(response);
}
