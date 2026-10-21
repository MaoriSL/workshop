/**
 * Point d'entrée unique de la couche réseau.
 * Les pages importent depuis "@/api" et ne manipulent jamais fetch directement.
 */
export { API_URL, USE_MOCK, UNAUTHORIZED_EVENT, ApiError, getErrorMessage } from './client'
export { login, signup, logout, getCurrentUser } from './auth'
export { getAccount, listTransactions, getTransaction, sendMoney } from './transactions'
