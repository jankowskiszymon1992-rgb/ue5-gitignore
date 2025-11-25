import http from "./axiosInstance";

export const projectsApi = {
  async getStats() {
    return http.get("/api/projects/stats");
  },
  async listProjects() {
    return http.get("/api/projects");
  },
  async addProject(payload) {
    return http.post("/api/projects", payload);
  }
};

export const authApi = {
  async login(username, password) {
    return http.post("/api/auth/login", { username, password });
  },
  async me() {
    return http.get("/api/auth/me");
  }
};